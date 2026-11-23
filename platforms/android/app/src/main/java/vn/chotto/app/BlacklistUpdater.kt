package vn.chotto.app

import android.content.Context
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.Worker
import androidx.work.WorkerParameters
import java.io.File
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest
import java.util.concurrent.TimeUnit
import org.json.JSONArray
import org.json.JSONObject

/**
 * Cập nhật danh sách đen từ `rules.json › blacklist_sources`, cùng quy tắc an toàn với `tier1.update_from_sources`:
 * - chỉ HTTPS; vượt kích thước, trả HTML hoặc ít hơn `min_entries` mục hợp lệ bị coi là lỗi;
 * - nguồn trả 304 hoặc tạm lỗi thì dùng lại bản sao của chính nó (ETag/Last-Modified lưu theo nguồn);
 * - không nguồn nào có dữ liệu mới ⇒ giữ nguyên danh sách;
 * - có nguồn lỗi mà chưa có bản sao ⇒ gộp thêm danh sách hiện tại để không mất dữ liệu;
 * - danh sách mới nhỏ hơn 50% danh sách cũ (≥ 1000 mục) ⇒ từ chối.
 */
object BlacklistUpdater {
    private const val SHRINK_RATIO = 0.5
    private const val SHRINK_MIN_EXISTING = 1000
    private const val DAY_MS = 86_400_000L
    private const val RETRY_MS = 3_600_000L

    private class LongBuilder {
        var data = LongArray(1024)
        var size = 0
        fun add(v: Long) { if (size == data.size) data = data.copyOf(size * 2); data[size++] = v }
        fun toArray(): LongArray = data.copyOf(size)
    }

    private class Prefs(context: Context) {
        private val p = context.applicationContext.getSharedPreferences("chotto_update", Context.MODE_PRIVATE)
        var lastSuccess: Long get() = p.getLong("last_success", 0); set(v) = p.edit().putLong("last_success", v).apply()
        var lastAttempt: Long get() = p.getLong("last_attempt", 0); set(v) = p.edit().putLong("last_attempt", v).apply()
    }

    fun lastSuccess(context: Context): Long = Prefs(context).lastSuccess

    /** Đã đến lúc tự cập nhật: lần thành công cuối quá 24 giờ và lần thử cuối quá 1 giờ. */
    fun isDue(context: Context, now: Long = System.currentTimeMillis()): Boolean {
        val p = Prefs(context)
        if (p.lastAttempt != 0L && now - p.lastAttempt < RETRY_MS) return false
        return p.lastSuccess == 0L || now - p.lastSuccess >= DAY_MS
    }

    /** Bật/tắt lịch tự cập nhật hằng ngày (WorkManager, chỉ chạy khi có mạng) và chạy ngay nếu đã đến hạn. */
    fun schedule(context: Context, enabled: Boolean) {
        val wm = WorkManager.getInstance(context.applicationContext)
        if (!enabled) {
            wm.cancelUniqueWork("chotto-blacklist-daily")
            wm.cancelUniqueWork("chotto-blacklist-now")
            return
        }
        val net = Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()
        wm.enqueueUniquePeriodicWork(
            "chotto-blacklist-daily", ExistingPeriodicWorkPolicy.KEEP,
            PeriodicWorkRequestBuilder<UpdateWorker>(1, TimeUnit.DAYS).setConstraints(net).build(),
        )
        if (isDue(context)) {
            wm.enqueueUniqueWork(
                "chotto-blacklist-now", ExistingWorkPolicy.KEEP,
                OneTimeWorkRequestBuilder<UpdateWorker>().setConstraints(net).build(),
            )
        }
    }

    /**
     * Tải các nguồn và dựng lại danh sách. Chạy trên luồng nền.
     * @return số mục trong danh sách mới, hoặc 0 nếu danh sách không được thay.
     */
    fun update(context: Context, rules: Rules, blacklist: Blacklist, sink: (String) -> Unit = {}): Int {
        val log: (String) -> Unit = { android.util.Log.i("CHOTTO-update", it); sink(it) }
        val app = context.applicationContext
        val prefs = Prefs(app)
        val dir = File(app.filesDir, "sources").apply { mkdirs() }
        val collected = mutableListOf<LongArray>()
        var changed = 0
        var unchanged = 0
        var lost = 0
        for (source in rules.blacklistSources) {
            val base = File(dir, sha(source.url).take(24))
            val txt = File(base.path + ".txt")
            val meta = File(base.path + ".json")
            val (etag, modified) = validators(meta, txt)
            val tmpBody = File(base.path + ".body")
            val tmpTxt = File(base.path + ".txt.tmp")
            try {
                val fetched = download(source.url, rules.blacklistMaxBytes, etag, modified, tmpBody)
                if (fetched.notModified) {
                    if (!txt.exists()) throw IOException("máy chủ báo không đổi nhưng mất bản sao cục bộ")
                    val (fps, valid) = collectCached(blacklist, txt)
                    collected += fps
                    unchanged++
                    log("${source.name}: không đổi ($valid)")
                    continue
                }
                val (fps, valid) = tmpTxt.bufferedWriter().use { w ->
                    collect(blacklist, entriesOf(tmpBody), w)
                }
                if (valid < source.minEntries) throw IOException("chỉ có $valid mục hợp lệ (cần ${source.minEntries})")
                if (!tmpTxt.renameTo(txt)) { txt.delete(); tmpTxt.renameTo(txt) }
                meta.writeText(JSONObject().put("etag", fetched.etag).put("last_modified", fetched.lastModified).toString())
                collected += fps
                changed++
                log("${source.name}: $valid mục")
            } catch (e: Exception) {
                log("${source.name}: lỗi ${e.message}")
                if (txt.exists()) {
                    runCatching { collectCached(blacklist, txt).first }
                        .onSuccess { collected += it }.onFailure { lost++ }
                } else lost++
            } finally {
                tmpBody.delete(); tmpTxt.delete()
            }
        }
        val now = System.currentTimeMillis()
        prefs.lastAttempt = now
        if (changed + unchanged > 0) prefs.lastSuccess = now
        if (changed == 0) return 0

        val existing = blacklist.existing()
        val merged = LongBuilder()
        collected.forEach { arr -> arr.forEach(merged::add) }
        val newCount = FingerprintSet.of(merged.toArray()).size
        if (lost > 0) {
            existing.forEach(merged::add)
        } else if (existing.size >= SHRINK_MIN_EXISTING && newCount < SHRINK_RATIO * existing.size) {
            log("Danh sách mới ($newCount mục) nhỏ bất thường so với hiện tại (${existing.size}), giữ danh sách cũ.")
            return 0
        }
        blacklist.seedLines().mapNotNull(blacklist::acceptedKey).forEach { merged.add(FingerprintSet.fingerprint(it)) }
        val result = FingerprintSet.of(merged.toArray())
        blacklist.replace(result)
        return result.size
    }

    private fun collectCached(bl: Blacklist, txt: File): Pair<LongArray, Int> =
        txt.bufferedReader().use { collect(bl, it.lineSequence(), null) }

    /** Chuyển các dòng nguồn thành dấu vân tay; ghi các dòng hợp lệ ra `cache` (nếu có). Trả (vân tay, số dòng hợp lệ). */
    private fun collect(bl: Blacklist, lines: Sequence<String>, cache: java.io.Writer?): Pair<LongArray, Int> {
        val out = LongBuilder()
        var valid = 0
        for (line in lines) {
            if (BlacklistEntry.keys(line) == null) continue
            valid++
            cache?.apply { write(line); write("\n") }
            bl.acceptedKey(line)?.let { out.add(FingerprintSet.fingerprint(it)) }
        }
        return out.toArray() to valid
    }

    // ---- Tải & đọc nguồn -----------------------------------------------------------------------

    private class Fetched(val notModified: Boolean, val etag: String, val lastModified: String)

    private fun validators(meta: File, txt: File): Pair<String, String> = try {
        if (!txt.exists()) "" to "" else JSONObject(meta.readText()).let { it.optString("etag") to it.optString("last_modified") }
    } catch (_: Exception) { "" to "" }

    private fun download(url: String, maxBytes: Long, etag: String, modified: String, dest: File): Fetched {
        if (!url.lowercase().startsWith("https://")) throw IOException("chỉ chấp nhận nguồn HTTPS")
        val conn = URL(url).openConnection() as HttpURLConnection
        try {
            conn.connectTimeout = 20_000
            conn.readTimeout = 30_000
            conn.setRequestProperty("User-Agent", "CHOTTO-Android/1.0")
            if (etag.isNotEmpty()) conn.setRequestProperty("If-None-Match", etag)
            if (modified.isNotEmpty()) conn.setRequestProperty("If-Modified-Since", modified)
            val code = conn.responseCode
            if (code == 304) return Fetched(true, etag, modified)
            if (code !in 200..299) throw IOException("HTTP $code")
            var total = 0L
            conn.inputStream.use { input ->
                dest.outputStream().buffered().use { out ->
                    val buf = ByteArray(64 * 1024)
                    while (true) {
                        val n = input.read(buf)
                        if (n < 0) break
                        total += n
                        if (total > maxBytes) throw IOException("nguồn vượt quá $maxBytes byte")
                        out.write(buf, 0, n)
                    }
                }
            }
            return Fetched(false, conn.getHeaderField("ETag") ?: "", conn.getHeaderField("Last-Modified") ?: "")
        } finally {
            conn.disconnect()
        }
    }

    /** JSON (list/dict), CSV PhishTank hoặc văn bản mỗi dòng một mục (giống `tier1._parse_source`). */
    private fun entriesOf(file: File): Sequence<String> {
        val head = String(file.inputStream().use { readUpTo(it, 64) }, Charsets.UTF_8).trimStart(Char(0xFEFF), ' ', '\n', '\r', '\t')
        if (head.isEmpty()) return emptySequence()
        return when {
            head[0] == '[' || head[0] == '{' -> jsonEntries(file.readText().trimStart(Char(0xFEFF)))
            head.lowercase().startsWith("phish_id") -> csvUrls(file)
            head.lowercase().startsWith("<!doctype") || head.lowercase().startsWith("<html") ->
                throw IOException("nguồn trả về trang HTML thay vì danh sách")
            else -> file.bufferedReader().lineSequence()
        }
    }

    private fun jsonEntries(text: String): Sequence<String> {
        var arr: JSONArray? = null
        if (text.trimStart().startsWith("[")) arr = JSONArray(text) else {
            val o = JSONObject(text)
            for (k in o.keys()) if (o.get(k) is JSONArray) { arr = o.getJSONArray(k); break }
        }
        val a = arr ?: return emptySequence()
        return sequence {
            for (i in 0 until a.length()) {
                when (val item = a.get(i)) {
                    is String -> yield(item)
                    is JSONObject -> listOf("url", "domain", "host").firstNotNullOfOrNull { item.optString(it).ifEmpty { null } }?.let { yield(it) }
                }
            }
        }
    }

    /** Cột `url` của CSV PhishTank (có ngoặc kép, dấu phẩy trong ngoặc). */
    private fun csvUrls(file: File): Sequence<String> = sequence {
        file.bufferedReader().use { r ->
            val header = splitCsv(r.readLine() ?: return@sequence)
            val col = header.indexOf("url")
            if (col < 0) return@sequence
            for (line in r.lineSequence()) {
                val cells = splitCsv(line)
                if (col < cells.size && cells[col].isNotEmpty()) yield(cells[col])
            }
        }
    }

    private fun splitCsv(line: String): List<String> {
        val cells = mutableListOf<String>()
        val sb = StringBuilder()
        var quoted = false
        var i = 0
        while (i < line.length) {
            val c = line[i]
            when {
                quoted && c == '"' && i + 1 < line.length && line[i + 1] == '"' -> { sb.append('"'); i++ }
                c == '"' -> quoted = !quoted
                c == ',' && !quoted -> { cells += sb.toString(); sb.clear() }
                else -> sb.append(c)
            }
            i++
        }
        cells += sb.toString()
        return cells
    }

    private fun sha(s: String): String =
        MessageDigest.getInstance("SHA-256").digest(s.toByteArray()).joinToString("") { "%02x".format(it) }
}

/** Tác vụ nền cập nhật danh sách đen (WorkManager gọi, chỉ khi có mạng). */
class UpdateWorker(context: Context, params: WorkerParameters) : Worker(context, params) {
    override fun doWork(): Result {
        if (!Settings(applicationContext).autoUpdate) return Result.success()
        Shield.get(applicationContext).updateBlacklist()
        return Result.success()
    }
}
