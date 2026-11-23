package vn.chotto.app

import java.net.IDN

/**
 * Public Suffix List (cùng file `public_suffix_list.dat` với bản Desktop): xác định tên miền đăng ký được,
 * ví dụ `a.b.vietcombank.com.vn` → `vietcombank.com.vn`. Tương đương `chotto/core/psl.py`.
 */
class Psl private constructor(
    private val exact: Map<String, Boolean>,
    private val wildcard: Map<String, Boolean>,
    private val exception: Map<String, Boolean>,
) {
    /** `suffix`: hậu tố công cộng dài nhất khớp; `isPrivate`: thuộc mục PRIVATE; `registrable`: `null` nếu host là hậu tố. */
    data class Info(val suffix: String, val isPrivate: Boolean, val registrable: String?)

    fun lookup(host: String): Info {
        val labels = host.lowercase().trimEnd('.').split('.').filter { it.isNotEmpty() }
        val n = labels.size
        if (n == 0) return Info("", false, null)
        for (i in 0 until n) {
            val flag = exception[labels.subList(i, n).joinToString(".")]
            if (flag != null) return info(labels, n - i - 1, flag)
        }
        var suffixLen = 1
        var isPrivate = false
        for (i in 0 until n) {
            val exactFlag = exact[labels.subList(i, n).joinToString(".")]
            if (exactFlag != null) { suffixLen = n - i; isPrivate = exactFlag; break }
            if (i + 1 < n) {
                val wild = wildcard[labels.subList(i + 1, n).joinToString(".")]
                if (wild != null) { suffixLen = n - i; isPrivate = wild; break }
            }
        }
        return info(labels, suffixLen, isPrivate)
    }

    /** Tên miền đăng ký được của `host` (IP hoặc hậu tố công cộng: trả lại chính nó). */
    fun registeredDomain(host: String): String =
        if (host.isEmpty() || Url.isIpHost(host)) host else lookup(host).registrable ?: host

    /** `host` rồi các tên miền cha, dừng ở tên miền đăng ký được (không bao giờ sinh `com.vn`). */
    fun parentDomains(host: String): List<String> {
        if (host.isEmpty()) return emptyList()
        val out = mutableListOf(host)
        if (Url.isIpHost(host)) return out
        val registrable = lookup(host).registrable
        if (registrable == null || registrable == host) return out
        val labels = host.split('.')
        val stop = registrable.split('.').size
        for (i in 1..(labels.size - stop)) out += labels.subList(i, labels.size).joinToString(".")
        return out
    }

    private fun info(labels: List<String>, suffixLen: Int, isPrivate: Boolean): Info {
        val suffix = if (suffixLen > 0) labels.takeLast(suffixLen).joinToString(".") else ""
        val registrable = if (labels.size > suffixLen) labels.takeLast(suffixLen + 1).joinToString(".") else null
        return Info(suffix, isPrivate, registrable)
    }

    companion object {
        fun parse(text: String): Psl {
            val exact = HashMap<String, Boolean>(10_000)
            val wildcard = HashMap<String, Boolean>()
            val exception = HashMap<String, Boolean>()
            var private = false
            for (line in text.lineSequence()) {
                if (line.contains("===BEGIN PRIVATE DOMAINS===")) private = true
                val rule = line.trim().substringBefore(' ').substringBefore('\t')
                if (rule.isEmpty() || rule.startsWith("//")) continue
                val (kind, body) = when {
                    rule.startsWith("!") -> exception to rule.substring(1)
                    rule.startsWith("*.") -> wildcard to rule.substring(2)
                    else -> exact to rule
                }
                val ascii = try { IDN.toASCII(body, IDN.ALLOW_UNASSIGNED).lowercase() } catch (_: Exception) { continue }
                kind[ascii] = private
            }
            require(exact.isNotEmpty()) { "Public Suffix List rỗng" }
            return Psl(exact, wildcard, exception)
        }
    }
}

/** Đọc tối đa `max` byte (thay `InputStream.readNBytes`, vốn chỉ có từ Android 13 / API 33). */
fun readUpTo(input: java.io.InputStream, max: Int): ByteArray {
    val out = java.io.ByteArrayOutputStream()
    val buf = ByteArray(8192)
    while (out.size() < max) {
        val n = input.read(buf, 0, minOf(buf.size, max - out.size()))
        if (n < 0) break
        out.write(buf, 0, n)
    }
    return out.toByteArray()
}
