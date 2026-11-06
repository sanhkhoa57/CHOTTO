package vn.chotto.app

import android.content.Context
import java.io.File
import java.net.HttpURLConnection
import java.net.InetSocketAddress
import java.net.Socket
import java.net.URL
import java.time.Instant
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.OffsetDateTime
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.util.Locale
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit
import org.json.JSONObject

/**
 * Tầng 3: tuổi đời tên miền qua RDAP và WHOIS, port từ `chotto/tier3.py`.
 * - RDAP và WHOIS chạy song song trên luồng nền; kết quả đầu tiên có ngày đăng ký thắng.
 * - RDAP hỏi máy chủ nhà đăng ký theo bảng IANA bootstrap lưu cục bộ (làm mới mỗi 7 ngày), thiếu thì dùng rdap.org.
 * - `timeout` là TỔNG thời gian chờ: hết hạn là trả `null` ngay, luồng còn dở bị bỏ lại.
 * - Cache theo tên miền đăng ký: thành công 48 giờ, thất bại 1 giờ. Lỗi mạng trả `null` (engine dùng điểm Tầng 2).
 */
class AgeLookup(context: Context, private val rules: Rules) {
    data class Age(val days: Double, val org: String = "")

    private val app = context.applicationContext
    private val cache = app.getSharedPreferences("chotto_age_cache", Context.MODE_PRIVATE)
    private val bootstrapFile = File(app.filesDir, "rdap_bootstrap.json")
    @Volatile private var bootstrap: Map<String, String>? = null
    @Volatile private var bootstrapRefreshing = false

    private class Found(val created: Instant?, val org: String)

    fun lookup(host: String, timeoutSec: Double = 1.8, ttlHours: Double = 48.0): Age? {
        if (host.isEmpty() || Url.isIpHost(host)) return null
        val domain = rules.psl.lookup(host).registrable ?: return null
        val now = System.currentTimeMillis()
        cached(domain, ttlHours, now)?.let { return if (it.second) it.first else null }

        val deadline = System.nanoTime() + (maxOf(0.1, timeoutSec) * 1e9).toLong()
        val found = race(domain, deadline)
        if (found.created == null) {
            // Chỉ nhớ thất bại khi các nguồn đã trả lời; hết giờ thì lần sau thử lại.
            if (System.nanoTime() < deadline) put(domain, null, found.org, now)
            return null
        }
        put(domain, found.created.toEpochMilli(), found.org, now)
        return Age(maxOf(0.0, (now - found.created.toEpochMilli()) / 86_400_000.0), found.org)
    }

    // ---- Cache ----------------------------------------------------------------------------------

    /** (kết quả, có kết quả không) nếu cache còn hạn; `null` nếu phải tra mới. */
    private fun cached(domain: String, ttlHours: Double, now: Long): Pair<Age?, Boolean>? {
        val raw = cache.getString(domain, null) ?: return null
        val p = raw.split('|')
        if (p.size < 4) return null
        val created = p[0].toLongOrNull()
        val fetched = p[2].toLongOrNull() ?: return null
        val ok = p[3] == "1" && created != null
        val ttl = if (ok) (ttlHours * 3_600_000).toLong() else FAILURE_TTL_MS
        if (now - fetched >= ttl) return null
        return if (ok) Age(maxOf(0.0, (now - created!!) / 86_400_000.0), p[1]) to true else null to false
    }

    private fun put(domain: String, created: Long?, org: String, now: Long) {
        val e = cache.edit()
        if (cache.all.size > 2000) e.clear()
        e.putString(domain, "${created ?: ""}|${org.replace('|', ' ')}|$now|${if (created != null) 1 else 0}").apply()
    }

    // ---- RDAP + WHOIS song song -------------------------------------------------------------------

    private fun race(domain: String, deadline: Long): Found {
        // LinkedBlockingQueue không nhận null: nguồn lỗi/hết giờ báo bằng Found rỗng (created = null).
        val results = LinkedBlockingQueue<Found>()
        val workers = listOf<(String, Long) -> Found>(::rdap, ::whois)
        for (fetch in workers) {
            Thread {
                val found = try { fetch(domain, deadline) } catch (_: Throwable) { Found(null, "") }
                results.offer(found)
            }.apply { isDaemon = true; name = "chotto-tier3" }.start()
        }
        var orgFallback = ""
        repeat(workers.size) {
            val left = deadline - System.nanoTime()
            if (left <= 0) return Found(null, orgFallback)
            val item = results.poll(left, TimeUnit.NANOSECONDS) ?: return Found(null, orgFallback)
            if (item.created != null) return item
            if (orgFallback.isEmpty()) orgFallback = item.org
        }
        return Found(null, orgFallback)
    }

    private fun remainingMs(deadline: Long): Int {
        val ms = (deadline - System.nanoTime()) / 1_000_000
        if (ms <= 0) throw java.io.IOException("hết thời gian")
        return ms.coerceAtMost(Int.MAX_VALUE.toLong()).toInt()
    }

    private fun rdap(domain: String, deadline: Long): Found {
        val conn = URL(rdapUrl(domain)).openConnection() as HttpURLConnection
        try {
            val ms = remainingMs(deadline)
            conn.connectTimeout = ms
            conn.readTimeout = ms
            conn.setRequestProperty("Accept", "application/rdap+json")
            conn.setRequestProperty("User-Agent", "CHOTTO-Android/1.0")
            if (conn.responseCode !in 200..299) throw java.io.IOException("RDAP ${conn.responseCode}")
            val body = conn.inputStream.use { readUpTo(it, MAX_RDAP_BYTES + 1) }
            if (body.size > MAX_RDAP_BYTES) throw java.io.IOException("phản hồi RDAP quá lớn")
            val data = JSONObject(String(body, Charsets.UTF_8))
            var created: Instant? = null
            data.optJSONArray("events")?.let { ev ->
                for (i in 0 until ev.length()) {
                    val e = ev.optJSONObject(i) ?: continue
                    if (e.optString("eventAction") == "registration") {
                        val c = parseDate(e.optString("eventDate"))
                        if (c != null && (created == null || c.isBefore(created))) created = c
                    }
                }
            }
            var org = ""
            data.optJSONArray("entities")?.let { en ->
                for (i in 0 until en.length()) {
                    val ent = en.optJSONObject(i) ?: continue
                    val roles = ent.optJSONArray("roles") ?: continue
                    if ((0 until roles.length()).none { roles.optString(it) == "registrant" }) continue
                    val items = ent.optJSONArray("vcardArray")?.optJSONArray(1) ?: continue
                    for (j in 0 until items.length()) {
                        val item = items.optJSONArray(j) ?: continue
                        if (item.length() > 3 && item.optString(0) in listOf("fn", "org")) org = item.opt(3)?.toString().orEmpty()
                    }
                }
            }
            return Found(created, org)
        } finally {
            conn.disconnect()
        }
    }

    private fun whoisQuery(server: String, query: String, deadline: Long): String {
        Socket().use { sock ->
            sock.connect(InetSocketAddress(server, 43), remainingMs(deadline))
            sock.getOutputStream().apply { write("$query\r\n".toByteArray(Charsets.US_ASCII)); flush() }
            val out = java.io.ByteArrayOutputStream()
            val buf = ByteArray(4096)
            while (out.size() < MAX_WHOIS_BYTES) {
                sock.soTimeout = remainingMs(deadline)
                val n = sock.getInputStream().read(buf)
                if (n < 0) break
                out.write(buf, 0, n)
            }
            return String(out.toByteArray(), Charsets.UTF_8)
        }
    }

    private fun whois(domain: String, deadline: Long): Found {
        val tld = domain.substringAfterLast('.')
        val referral = whoisQuery("whois.iana.org", tld, deadline)
        val server = REFER_RE.find(referral)?.groupValues?.get(1) ?: return Found(null, "")
        val text = whoisQuery(server, domain, deadline)
        val created = DATE_RE.find(text)?.groupValues?.get(1)?.let(::parseDate)
        val org = ORG_RE.find(text)?.groupValues?.get(1).orEmpty()
        return Found(created, org)
    }

    // ---- Bảng IANA bootstrap -----------------------------------------------------------------------

    private fun rdapUrl(domain: String): String {
        val base = bootstrapFor(domain.substringAfterLast('.'))
        return if (base == null) "https://rdap.org/domain/$domain" else "${base}domain/$domain"
    }

    private fun bootstrapFor(tld: String): String? {
        var table = bootstrap
        if (table == null) {
            table = runCatching { parseBootstrap(JSONObject(bootstrapFile.readText())) }.getOrNull()
            bootstrap = table
        }
        val age = System.currentTimeMillis() - bootstrapFile.lastModified()
        if (table == null || age > BOOTSTRAP_MAX_AGE_MS) refreshBootstrapInBackground()
        return table?.get(tld.lowercase())
    }

    private fun refreshBootstrapInBackground() {
        if (bootstrapRefreshing) return
        bootstrapRefreshing = true
        Thread {
            try {
                val conn = URL("https://data.iana.org/rdap/dns.json").openConnection() as HttpURLConnection
                conn.connectTimeout = 20_000; conn.readTimeout = 20_000
                val body = String(conn.inputStream.use { readUpTo(it, 2 shl 20) }, Charsets.UTF_8)
                val table = parseBootstrap(JSONObject(body))
                if (table.isNotEmpty()) { bootstrapFile.writeText(body); bootstrap = table }
            } catch (_: Exception) {
            } finally {
                bootstrapRefreshing = false
            }
        }.apply { isDaemon = true }.start()
    }

    private fun parseBootstrap(o: JSONObject): Map<String, String> {
        val services = o.getJSONArray("services")
        val table = HashMap<String, String>()
        for (i in 0 until services.length()) {
            val svc = services.optJSONArray(i) ?: continue
            val tlds = svc.optJSONArray(0) ?: continue
            val urls = svc.optJSONArray(1) ?: continue
            val base = (0 until urls.length()).map { urls.optString(it) }.firstOrNull { it.lowercase().startsWith("https://") } ?: continue
            val withSlash = if (base.endsWith("/")) base else "$base/"
            for (j in 0 until tlds.length()) table[tlds.optString(j).lowercase().trim('.')] = withSlash
        }
        return table
    }

    companion object {
        private const val FAILURE_TTL_MS = 3_600_000L
        private const val BOOTSTRAP_MAX_AGE_MS = 7 * 86_400_000L
        private const val MAX_RDAP_BYTES = 1 shl 20
        private const val MAX_WHOIS_BYTES = 64 * 1024
        private val DATE_RE = Regex(
            "^\\s*(?:creation date|created on|created|registered on|registration time|registration date|" +
                "domain registration date|registered|domain create date)\\s*:\\s*(.+?)\\s*$",
            setOf(RegexOption.IGNORE_CASE, RegexOption.MULTILINE),
        )
        private val REFER_RE = Regex("^(?:refer|whois):\\s*(\\S+)", setOf(RegexOption.IGNORE_CASE, RegexOption.MULTILINE))
        private val ORG_RE = Regex(
            "^\\s*registrant(?: organization| name)?\\s*:\\s*(.+?)\\s*$",
            setOf(RegexOption.IGNORE_CASE, RegexOption.MULTILINE),
        )
        private val DATE_PATTERNS = listOf(
            "yyyy-MM-dd HH:mm:ss", "yyyy.MM.dd HH:mm:ss", "yyyy/MM/dd HH:mm:ss", "dd-MMM-yyyy HH:mm:ss",
            "dd.MM.yyyy HH:mm:ss", "EEE MMM dd HH:mm:ss zzz yyyy",
        )
        private val DATE_ONLY_PATTERNS = listOf("yyyy-MM-dd", "yyyy.MM.dd", "yyyy/MM/dd", "dd-MMM-yyyy", "dd.MM.yyyy", "yyyyMMdd")

        /** Đọc ngày đăng ký từ chuỗi RDAP/WHOIS (ISO 8601 và các định dạng WHOIS phổ biến); lỗi trả `null`. */
        fun parseDate(text: String): Instant? {
            val value = text.trim().substringBefore(" (").trim()
            if (value.isEmpty()) return null
            runCatching { return OffsetDateTime.parse(value).toInstant() }
            runCatching { return Instant.parse(value) }
            runCatching { return LocalDateTime.parse(value).toInstant(ZoneOffset.UTC) }
            for (p in DATE_PATTERNS) runCatching {
                return LocalDateTime.parse(value, DateTimeFormatter.ofPattern(p, Locale.ENGLISH)).toInstant(ZoneOffset.UTC)
            }
            for (p in DATE_ONLY_PATTERNS) runCatching {
                return LocalDate.parse(value, DateTimeFormatter.ofPattern(p, Locale.ENGLISH)).atStartOfDay().toInstant(ZoneOffset.UTC)
            }
            return null
        }

        /**
         * Điểm cộng/trừ theo tuổi tên miền: nội suy tuyến tính trên `age_curve`. Tên miền mạo danh thương hiệu không
         * bao giờ được trừ điểm vì tuổi. Trả (điểm, lý do tiếng Việt hoặc rỗng khi điểm không dương).
         */
        fun ageAdjustment(ageDays: Double, curve: List<Pair<Double, Double>>, impersonates: Boolean): Pair<Int, String> {
            val age = maxOf(0.0, ageDays)
            var points = curve.last().second
            for (i in 0 until curve.size - 1) {
                val (d0, v0) = curve[i]
                val (d1, v1) = curve[i + 1]
                if (age <= d1) {
                    val span = d1 - d0
                    val ratio = if (span > 0) (age - d0) / span else 1.0
                    points = v0 + (v1 - v0) * ratio
                    break
                }
            }
            var adjust = Math.round(points).toInt()
            if (adjust < 0 && impersonates) adjust = 0
            return if (adjust > 0) adjust to "Tên miền mới đăng ký cách đây ${age.toInt()} ngày" else adjust to ""
        }
    }
}
