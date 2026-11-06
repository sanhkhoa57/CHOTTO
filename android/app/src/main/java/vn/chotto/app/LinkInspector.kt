package vn.chotto.app

import java.text.Normalizer
import java.util.Base64
import kotlin.math.abs
import kotlin.math.ln
import org.json.JSONArray
import org.json.JSONObject

/**
 * Bản rút gọn Tầng 2 (heuristics) của CHOTTO, port từ `chotto/tier2.py` / `extension/src/engine/tier2.js`.
 *
 * Dùng chung `rules.json` và `popular_vn.txt` với bản Desktop (chép vào `assets/`). Khác bản đầy đủ:
 * Đây là Tầng 2; Tầng 1 (danh sách đen) và Tầng 3 (tuổi tên miền) nằm ở [Shield]. Bảng ký tự đánh lừa thị giác
 * là bản rút gọn của `confusables_ascii.json`.
 * Không phân tích được link thì KHÔNG coi là an toàn (fail-safe: cảnh báo).
 */
class LinkInspector(val rules: Rules) {

    private val psl get() = rules.psl

    enum class Level { SAFE, WARN, HIGH, BLOCKED }

    data class Signal(val code: String, val points: Int, val reason: String, val brand: String = "")

    data class Result(
        val originalUrl: String,
        /** URL đích sau khi bóc các lớp bọc (zalo.me, l.facebook.com...); mở URL này nếu người dùng chọn "Vẫn mở". */
        val finalUrl: String,
        val host: String,
        val displayDomain: String,
        val riskScore: Int,
        val level: Level,
        val signals: List<Signal>,
        /** URL mở khi người dùng chọn "Vẫn mở" / link an toàn: link gốc (giống Desktop), không phải đích đã bóc. */
        val openUrl: String = originalUrl,
        /** Tầng đã phát hiện rủi ro: 1 = danh sách đen, 2 = heuristics, 3 = có tuổi tên miền. */
        val tier: Int = 2,
        val ageDays: Double? = null,
    ) {
        val isSuspicious: Boolean get() = level != Level.SAFE

        /** Tối đa 4 dấu hiệu mạnh nhất có điểm dương, viết theo ngôn ngữ `lang` ("vi" | "en"). */
        fun reasons(lang: String): List<String> = signals
            .filter { it.points > 0 && it.reason.isNotEmpty() }
            .sortedByDescending { it.points }
            .take(4)
            .map { Reasons.text(it, lang) }
    }

    /** Kết quả phân tích Tầng 2, trước khi quy ra mức rủi ro (Tầng 3 còn có thể cộng/trừ điểm). */
    class Analysis(
        val original: Url,
        val chain: List<Url>,
        val final: Url,
        val signals: List<Signal>,
        val trusted: Boolean,
    ) {
        val score: Int get() = signals.sumOf { it.points }.coerceIn(0, 100)
    }

    /** Chỉ Tầng 2 (không danh sách đen, không mạng). */
    fun inspect(raw: String): Result {
        val parsed = Url.parse(raw) ?: return unparseable(raw)
        return toResult(raw, analyze(parsed))
    }

    fun unparseable(raw: String): Result {
        val points = rules.weight("unparseable")
        return Result(
            raw, raw.take(2048), "", "", points, Level.WARN,
            listOf(Signal("unparseable", points, "CHOTTO không phân tích được liên kết này, hãy kiểm tra kỹ trước khi mở")),
            openUrl = safeOpenUrl(raw), tier = 0,
        )
    }

    fun analyze(parsed: Url): Analysis {
        val (chain, exhausted) = unwrap(parsed)
        var final = chain.last()
        var fullChain = chain
        val signals = mutableListOf<Signal>()

        if (!final.isIp && isTrusted(final.host)) {
            val embedded = embeddedUrls(final).firstOrNull { it.isIp || !isTrusted(it.host) }
            if (embedded == null) {
                if (chain.any { it.hasCredentials }) signals += sig("at_sign", "Chứa ký tự @ để che giấu tên miền thật")
                if (exhausted) signals += sig("nested_redirect", NESTED)
                return Analysis(parsed, chain, final, signals, trusted = true)
            }
            signals += sig("redirect_via_trusted", "Đi qua ${final.host} để chuyển hướng sang ${embedded.host}")
            fullChain = chain + embedded
            final = embedded
            signals.addAll(0, scoreUrl(final, fullChain, false))
        } else {
            signals += scoreUrl(final, fullChain, exhausted)
        }
        return Analysis(parsed, fullChain, final, signals, trusted = false)
    }

    /** Quy điểm ra mức rủi ro; `extra` là dấu hiệu thêm của Tầng 3 (tuổi tên miền). */
    fun toResult(raw: String, a: Analysis, extra: Signal? = null, tier: Int = 2, ageDays: Double? = null): Result {
        val signals = if (extra != null) a.signals + extra else a.signals
        val score = signals.sumOf { it.points }.coerceIn(0, 100)
        val level = when {
            score >= rules.threshold("high") -> Level.HIGH
            score >= rules.threshold("friction") -> Level.WARN
            else -> Level.SAFE
        }
        return Result(
            raw, a.final.href, a.final.host, registeredDomain(a.final.host), score, level, signals,
            openUrl = a.original.href, tier = tier, ageDays = ageDays,
        )
    }

    fun registeredDomain(host: String): String = psl.registeredDomain(host)

    /** URL an toàn để mở khi không phân tích được: bỏ ký tự điều khiển, percent-encode ký tự chèn tham số (như Desktop). */
    private fun safeOpenUrl(raw: String): String =
        raw.trim().filterNot { it.code < 0x20 || it.code in 0x7F..0x9F }
            .map { if (it in " \"<>`{}|\\^") "%%%02X".format(it.code) else it.toString() }.joinToString("")

    private fun sig(code: String, reason: String, weightKey: String = code) =
        Signal(code, rules.weight(weightKey), reason)

    // ---- Bóc link bọc -------------------------------------------------------------------------

    private fun unwrap(start: Url): Pair<List<Url>, Boolean> {
        val chain = mutableListOf(start)
        val seen = mutableSetOf(start.href)
        var current = start
        repeat(rules.threshold("unwrap_depth")) {
            val target = wrapperTarget(current).second
            if (target == null || !seen.add(target.href)) return chain to false
            current = target
            chain += target
        }
        return chain to wrapperTarget(current).first
    }

    private fun wrapperTarget(url: Url): Pair<Boolean, Url?> {
        val pairs = parseQsl(url.query, keepBlank = true)
        var isWrapper = false
        for (w in rules.wrappers) {
            val hostOk = if (w.suffixMatch) inDomain(url.host, w.host) else url.host == w.host
            if (!hostOk || !url.path.startsWith(w.path)) continue
            when (w.target) {
                "path" -> {
                    isWrapper = true
                    val rest = url.path.substring(w.path.length)
                    val q = if (url.query.isNotEmpty()) "?${url.query}" else ""
                    tryParse("${w.scheme}://$rest$q")?.let { return true to it }
                }
                "query" -> {
                    isWrapper = true
                    extractUrl(unquote(url.query))?.let { return true to it }
                }
                else -> {
                    val wildcard = "*" in w.params
                    val ordered = w.params.filter { it != "*" }.toMutableList()
                    if (wildcard) pairs.forEach { (k, _) -> if (k !in ordered) ordered += k }
                    for (name in ordered) for ((k, v) in pairs) {
                        if (k != name) continue
                        if (!wildcard) isWrapper = true
                        extractUrl(v)?.let { return true to it }
                    }
                }
            }
        }
        return isWrapper to null
    }

    fun embeddedUrls(url: Url): List<Url> {
        val own = registeredDomain(url.host)
        return parseQsl(url.query, keepBlank = false)
            .mapNotNull { extractUrl(it.second) }
            .filter { registeredDomain(it.host) != own }
            .take(5)
    }

    private fun isTrusted(host: String): Boolean =
        rules.trustedDomains.any { inDomain(host, it) } ||
            rules.brands.any { b -> b.domains.any { inDomain(host, it) } } ||
            registeredDomain(host) in rules.popularDomains

    // ---- Chấm điểm ----------------------------------------------------------------------------

    private fun scoreUrl(url: Url, chain: List<Url>, exhausted: Boolean): List<Signal> {
        val out = mutableListOf<Signal>()
        if (exhausted) out += sig("nested_redirect", NESTED)
        if (url.scheme == "http") out += sig("http", "Liên kết không mã hóa (http://)")
        if (chain.any { it.hasCredentials }) out += sig("at_sign", "Chứa ký tự @ để che giấu tên miền thật")
        if (url.port != null) out += sig("port", "Dùng cổng mạng bất thường (:${url.port})")
        if (registeredDomain(url.host) in rules.shorteners || url.host in rules.shorteners) {
            out += sig("shortener", "Link rút gọn che giấu địa chỉ đích thật")
        }
        var labels = emptyList<String>()
        if (url.isIp) {
            out += sig("raw_ip", "Dùng địa chỉ IP thay cho tên miền")
        } else {
            labels = attackerLabels(url.host)
            brandSignal(labels)?.let { out += it }
            out += lexicalSignals(labels, url.host)
        }
        lureSignal(labels, url)?.let { out += it }
        brandDomainInPath(url)?.let { out += it }
        return out
    }

    private fun brandSignal(labels: List<String>): Signal? {
        val ascii = labels.flatMap(::tokensOf)
        val unicode = labels.flatMap { tokensOf(toUnicode(it)) }
        var best: Signal? = null
        fun consider(s: Signal) { if (best == null || s.points > best!!.points) best = s }

        for (brand in rules.brands) for (rawKw in brand.keywords) {
            val kw = rawKw.lowercase()
            if (ascii.any { !it.startsWith("xn--") && keywordIn(it, kw) }) {
                consider(Signal("combosquat", rules.weight("combosquat"),
                    "Tên miền chứa tên “${brand.name}” nhưng không phải trang chính thức", brand.name))
                continue
            }
            if (unicode.any { t -> val shape = skeleton(t); shape != fold(t.lowercase()) && keywordIn(shape, kw) }) {
                consider(Signal("homoglyph", rules.weight("homoglyph"),
                    "Dùng ký tự đánh lừa thị giác (0/o, 1/l, rn/m, chữ Nga…) để mạo danh ${brand.name}", brand.name))
            }
            if (kw.length < 5) continue
            val limit = if (kw.length < 8) 1 else 2
            for (t in ascii) {
                if (t.length < 5 || abs(t.length - kw.length) > 2) continue
                val d = osaDistance(t, kw)
                if (d in 1..limit) {
                    consider(Signal("typosquat", rules.weight("typosquat"),
                        "Dấu hiệu mạo danh thương hiệu ${brand.name} (sai lệch $d ký tự)", brand.name))
                    break
                }
            }
        }
        return best
    }

    private fun keywordIn(token: String, kw: String): Boolean {
        if (kw.length >= 5) return kw in token
        if (token == kw) return true
        if (token.startsWith(kw)) return isAffixSequence(token.substring(kw.length))
        if (token.endsWith(kw)) return isAffixSequence(token.substring(0, token.length - kw.length))
        return false
    }

    /** `text` ghép được hoàn toàn từ phụ tố (bank, online, cskh...) và cụm chữ số. */
    private fun isAffixSequence(text: String): Boolean {
        val reach = BooleanArray(text.length + 1).also { it[0] = true }
        for (i in text.indices) {
            if (!reach[i]) continue
            var end = i
            while (end < text.length && text[end].isDigit()) { end++; reach[end] = true }
            for (a in rules.brandAffixes) if (text.startsWith(a, i)) reach[i + a.length] = true
        }
        return reach[text.length]
    }

    private fun lureSignal(labels: List<String>, url: Url): Signal? {
        val hostText = normalizeForMatching(labels.joinToString("-") { toUnicode(it) })
        val pathText = normalizeForMatching(url.pathAndQuery)
        val hostFlat = hostText.replace("-", "")
        val pathFlat = pathText.replace("-", "")
        val found = LinkedHashMap<String, String>()
        for (raw in rules.lureKeywords) {
            val display = raw.trim().split(Regex("\\s+")).joinToString(" ")
            val kw = normalizeForMatching(display)
            if (kw.isEmpty() || kw in found) continue
            val flat = kw.replace("-", "")
            if ("-$hostText-".contains("-$kw-") || "-$pathText-".contains("-$kw-") ||
                (flat.length >= 6 && flat in hostFlat) || (flat.length >= 7 && flat in pathFlat)
            ) found[kw] = display
        }
        if (found.isEmpty()) return null
        val keys = found.keys.toList()
        val distinct = keys.filter { k -> keys.none { o -> o != k && k in o } }
        val points = minOf(rules.weight("lure_cap"), rules.weight("lure_each") * distinct.size)
        return Signal("lure", points, "Chứa từ khóa gây hoang mang: “${found[distinct[0]]}”")
    }

    private fun brandDomainInPath(url: Url): Signal? {
        val text = unquote(url.pathAndQuery).lowercase()
        for (b in rules.brands) for (d in b.domains) {
            if (Regex("(?<![a-z0-9-])${Regex.escape(d.lowercase())}(?![a-z0-9-])").containsMatchIn(text)) {
                return Signal("brand_in_path", rules.weight("brand_in_path"),
                    "Đường dẫn chèn địa chỉ $d để giả làm trang của ${b.name}", b.name)
            }
        }
        return null
    }

    private fun lexicalSignals(labels: List<String>, host: String): List<Signal> {
        val out = mutableListOf<Signal>()
        val tld = host.substringAfterLast('.')
        if (tld in rules.highRiskTlds) out += sig("tld", "Đuôi .$tld thường bị lạm dụng để lừa đảo", "high_risk_tld")
        if (labels.any { it.startsWith("xn--") }) out += sig("idn", "Tên miền dùng ký tự Unicode dễ giả mạo")
        val plain = labels.filterNot { it.startsWith("xn--") }
        val joined = plain.joinToString("") { it.replace("-", "") }
        if (joined.length >= 8 && entropy(joined) > rules.entropyThreshold) {
            out += sig("entropy", "Tên miền trông như chuỗi ký tự ngẫu nhiên")
        }
        if (plain.sumOf { l -> l.count { it == '-' } } >= rules.threshold("hyphens")) {
            out += sig("hyphens", "Tên miền có nhiều dấu gạch ngang bất thường")
        }
        val digits = joined.count { it.isDigit() }
        if (digits >= 3 && digits.toDouble() / maxOf(joined.length, 1) > 0.3) {
            out += sig("digits", "Tên miền chứa nhiều chữ số ngẫu nhiên", "random_digits")
        }
        val info = psl.lookup(host)
        if (info.isPrivate && info.suffix.split('.').none { it in GOVERNMENT_LABELS }) {
            out += sig("free_hosting", "Trang nằm trên nền tảng tạo web miễn phí, ai cũng lập được trong vài phút")
        }
        return out
    }

    // ---- Tiện ích -----------------------------------------------------------------------------

    /** Nhãn do người đăng ký kiểm soát (bỏ hậu tố công cộng). */
    private fun attackerLabels(host: String): List<String> {
        val labels = host.split('.')
        val n = psl.lookup(host).suffix.let { if (it.isEmpty()) 0 else it.split('.').size }
        return if (n < labels.size) labels.subList(0, labels.size - n) else emptyList()
    }

    companion object {
        private const val NESTED = "Liên kết bị bọc qua quá nhiều lớp chuyển hướng để che đích thật"

        private val GOVERNMENT_LABELS = setOf("gov", "govt", "gob", "gouv", "mil")

        fun inDomain(host: String, domain: String): Boolean = host == domain || host.endsWith(".$domain")

        fun toUnicode(label: String): String =
            Url.domainToUnicode(label)

        fun fold(text: String): String =
            Normalizer.normalize(text.replace('đ', 'd').replace('Đ', 'D'), Normalizer.Form.NFD)
                .replace(Regex("\\p{Mn}+"), "")

        fun normalizeForMatching(text: String): String {
            var decoded = text
            repeat(3) { val next = unquote(decoded); if (next == decoded) return@repeat; decoded = next }
            return fold(Normalizer.normalize(decoded, Normalizer.Form.NFC).lowercase())
                .replace(Regex("[^a-z0-9]+"), "-").trim('-')
        }

        /** Chữ Nga/Hy Lạp hay dùng thay chữ Latin. */
        private val CONFUSABLES = mapOf(
            'а' to 'a', 'е' to 'e', 'о' to 'o', 'р' to 'p', 'с' to 'c', 'у' to 'y', 'х' to 'x', 'і' to 'i',
            'ј' to 'j', 'ѕ' to 's', 'ԁ' to 'd', 'ɡ' to 'g', 'һ' to 'h', 'ӏ' to 'l', 'ο' to 'o', 'ν' to 'v',
            'α' to 'a', 'ε' to 'e', 'ι' to 'i', 'κ' to 'k', 'τ' to 't', 'ʋ' to 'v', 'ı' to 'i',
        )
        private val DIGIT_HOMOGLYPHS = mapOf('0' to 'o', '1' to 'l', '3' to 'e', '5' to 's', '4' to 'a', '7' to 't', '8' to 'b')

        fun skeleton(text: String): String {
            var s = Normalizer.normalize(text, Normalizer.Form.NFKC).lowercase().map { CONFUSABLES[it] ?: it }.joinToString("")
            s = fold(s)
            for ((a, b) in listOf("rn" to "m", "vv" to "w", "nn" to "m")) s = s.replace(a, b)
            return s.map { DIGIT_HOMOGLYPHS[it] ?: it }.joinToString("")
        }

        fun tokensOf(label: String): List<String> =
            label.split(Regex("[-_]+")).filter { it.isNotEmpty() } + label.replace("-", "").replace("_", "")

        fun entropy(text: String): Double {
            val n = text.length.toDouble()
            return text.groupingBy { it }.eachCount().values.sumOf { c -> val p = c / n; -p * ln(p) / ln(2.0) }
        }

        /** Damerau–Levenshtein dạng OSA. */
        fun osaDistance(a: String, b: String): Int {
            val d = Array(a.length + 1) { IntArray(b.length + 1) }
            for (i in 0..a.length) d[i][0] = i
            for (j in 0..b.length) d[0][j] = j
            for (i in 1..a.length) for (j in 1..b.length) {
                val cost = if (a[i - 1] == b[j - 1]) 0 else 1
                d[i][j] = minOf(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
                if (i > 1 && j > 1 && a[i - 1] == b[j - 2] && a[i - 2] == b[j - 1]) d[i][j] = minOf(d[i][j], d[i - 2][j - 2] + 1)
            }
            return d[a.length][b.length]
        }

        /** `urllib.parse.unquote` của Python: giải từng cụm `%XX` hợp lệ theo UTF-8 (lỗi ⇒ U+FFFD), `%` hỏng giữ nguyên. */
        fun unquote(s: String): String {
            if (!s.contains('%')) return s
            return PERCENT_RUN.replace(s) { m -> String(Url.percentDecode(m.value), Charsets.UTF_8) }
        }
        private val PERCENT_RUN = Regex("(?:%[0-9A-Fa-f]{2})+")

        fun parseQsl(query: String, keepBlank: Boolean): List<Pair<String, String>> =
            query.split('&').filter { it.isNotEmpty() }.mapNotNull { nv ->
                val eq = nv.indexOf('=')
                val (k, v) = if (eq < 0) nv to "" else nv.substring(0, eq) to nv.substring(eq + 1)
                if (eq < 0 && !keepBlank) null
                else if (v.isEmpty() && !keepBlank) null
                else unquote(k.replace('+', ' ')) to unquote(v.replace('+', ' '))
            }

        fun tryParse(candidate: String): Url? {
            var t = candidate.trim()
            if (t.startsWith("//")) t = "https:$t"
            val low = t.lowercase()
            if (!low.startsWith("http://") && !low.startsWith("https://")) return null
            return Url.parse(t)
        }

        /** Đọc tham số của link bọc thành URL: nguyên bản, giải `%` thêm 1–2 lớp, hoặc base64. */
        fun extractUrl(value: String): Url? {
            val candidates = mutableListOf(value)
            repeat(2) { candidates += unquote(candidates.last()) }
            val raw = value.trim()
            if (raw.isNotEmpty() && raw.length <= 8192) {
                try {
                    val padded = raw + "=".repeat((4 - raw.length % 4) % 4)
                    val bytes = Base64.getDecoder().decode(padded.replace('-', '+').replace('_', '/'))
                    val decoder = Charsets.UTF_8.newDecoder()
                    candidates += decoder.decode(java.nio.ByteBuffer.wrap(bytes)).toString()
                } catch (_: Exception) { /* không phải base64/UTF-8 */ }
            }
            return candidates.firstNotNullOfOrNull { tryParse(it) }
        }
    }
}

/** Bộ luật đọc từ `rules.json` (chung với bản Desktop). */
class Rules(
    val thresholds: Map<String, Double>,
    val weights: Map<String, Int>,
    val highRiskTlds: Set<String>,
    val lureKeywords: List<String>,
    val shorteners: Set<String>,
    val wrappers: List<Wrapper>,
    val trustedDomains: List<String>,
    val brands: List<Brand>,
    val brandAffixes: List<String>,
    val popularDomains: Set<String>,
    val ageCurve: List<Pair<Double, Double>>,
    val psl: Psl,
    val blacklistSources: List<BlacklistSource>,
    val blacklistMaxBytes: Long,
) {
    data class BlacklistSource(val name: String, val url: String, val minEntries: Int)
    data class Brand(val name: String, val keywords: List<String>, val domains: List<String>)
    data class Wrapper(
        val host: String, val path: String, val suffixMatch: Boolean,
        val target: String, val scheme: String, val params: List<String>,
    )

    fun weight(key: String): Int = weights[key] ?: 0
    fun threshold(key: String): Int = thresholds[key]?.toInt() ?: 0
    val entropyThreshold: Double get() = thresholds["entropy"] ?: 3.65

    companion object {
        fun parse(rulesJson: String, popularTxt: String, pslTxt: String): Rules {
            val o = JSONObject(rulesJson)
            fun strings(a: JSONArray?): List<String> = a?.let { arr -> List(arr.length()) { arr.getString(it) } } ?: emptyList()
            val th = o.getJSONObject("thresholds")
            val w = o.getJSONObject("weights")
            val brands = o.getJSONArray("brands").let { a ->
                List(a.length()) { i ->
                    val b = a.getJSONObject(i)
                    Brand(b.getString("name"), strings(b.optJSONArray("keywords")), strings(b.optJSONArray("domains")))
                }
            }
            val wrappers = o.getJSONArray("wrappers").let { a ->
                List(a.length()) { i ->
                    val x = a.getJSONObject(i)
                    Wrapper(
                        x.getString("host"), x.getString("path"), x.optString("match") == "suffix",
                        x.optString("target", "params"), x.optString("scheme", "https"), strings(x.optJSONArray("params")),
                    )
                }
            }
            val popular = popularTxt.lineSequence()
                .map { it.trim() }
                .filter { it.isNotEmpty() && !it.startsWith("#") }
                .map { it.substringBefore('\t').trim().lowercase() }
                .toSet()
            return Rules(
                thresholds = th.keys().asSequence().associateWith { th.getDouble(it) },
                weights = w.keys().asSequence().associateWith { w.getInt(it) },
                highRiskTlds = strings(o.optJSONArray("high_risk_tlds")).toSet(),
                lureKeywords = strings(o.optJSONArray("lure_keywords")),
                shorteners = strings(o.optJSONArray("shorteners")).toSet(),
                wrappers = wrappers,
                trustedDomains = strings(o.optJSONArray("trusted_domains")),
                brands = brands,
                brandAffixes = strings(o.optJSONArray("brand_affixes")).map { it.lowercase() }.filter { it.isNotEmpty() },
                popularDomains = popular,
                ageCurve = o.getJSONArray("age_curve").let { a ->
                    List(a.length()) { i -> a.getJSONArray(i).let { it.getDouble(0) to it.getDouble(1) } }
                },
                psl = Psl.parse(pslTxt),
                blacklistSources = o.optJSONArray("blacklist_sources")?.let { a ->
                    List(a.length()) { i ->
                        val x = a.getJSONObject(i)
                        BlacklistSource(x.optString("name", "?"), x.getString("url"), x.optInt("min_entries", 1))
                    }
                } ?: emptyList(),
                blacklistMaxBytes = o.optLong("blacklist_max_bytes", 64L * 1024 * 1024),
            )
        }
    }
}
