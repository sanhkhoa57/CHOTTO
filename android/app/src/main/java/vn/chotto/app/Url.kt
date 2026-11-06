package vn.chotto.app

import java.net.Inet4Address
import java.net.Inet6Address
import java.net.InetAddress
import java.text.Normalizer

/**
 * URL http/https đã chuẩn hóa, đọc đúng như trình duyệt (WHATWG URL Standard). Port 1-1 của `chotto/core/url.py`:
 * mọi tầng thẩm định phải nhìn URL giống hệt trang trình duyệt sẽ mở, ví dụ `https://evil.top\@vietcombank.com.vn/`
 * mở `evil.top`, `http://3232235777/` mở `192.168.1.1`.
 */
class Url private constructor(
    val scheme: String,
    val username: String,
    val password: String,
    /** ASCII chữ thường (punycode cho IDN); IPv4 dạng chấm; IPv6 trong ngoặc vuông; không có dấu chấm cuối. */
    val host: String,
    private val hostKind: HostKind,
    /** Cổng nếu khác cổng mặc định của scheme. */
    val port: Int?,
    /** Luôn bắt đầu bằng `/`. */
    val path: String,
    private val queryOrNull: String?,
    private val fragmentOrNull: String?,
) {
    enum class HostKind { DOMAIN, IPV4, IPV6 }

    val query: String get() = queryOrNull ?: ""
    val fragment: String get() = fragmentOrNull ?: ""
    val hasCredentials: Boolean get() = username.isNotEmpty() || password.isNotEmpty()
    val isIp: Boolean get() = hostKind != HostKind.DOMAIN
    val pathAndQuery: String get() = if (queryOrNull == null) path else "$path?$queryOrNull"

    /** Chuỗi URL chuẩn hóa, an toàn để chuyển cho trình duyệt. */
    val href: String by lazy {
        buildString {
            append(scheme).append("://")
            if (hasCredentials) {
                append(username)
                if (password.isNotEmpty()) append(':').append(password)
                append('@')
            }
            append(host)
            if (port != null) append(':').append(port)
            append(path)
            if (queryOrNull != null) append('?').append(queryOrNull)
            if (fragmentOrNull != null) append('#').append(fragmentOrNull)
        }
    }

    private class ParseError(message: String) : Exception(message)

    companion object {
        const val MAX_URL_LENGTH = 32_768
        private val DEFAULT_PORTS = mapOf("http" to 80, "https" to 443)
        private val SCHEME_RE = Regex("^([A-Za-z][A-Za-z0-9+\\-.]*):")
        private val IPV4_DOTTED = Regex("""\d{1,3}(\.\d{1,3}){3}""")

        /** Ký tự UTS #46 ánh xạ thành rỗng (trình duyệt bỏ đi im lặng). */
        private val MAPPED_TO_NOTHING: Set<Int> =
            setOf(0xAD, 0x34F, 0x180B, 0x180C, 0x180D, 0x180F, 0x200B, 0x2060, 0xFEFF) + (0xFE00..0xFE0F)
        private val IDEOGRAPHIC_DOTS = setOf('。', '．', '｡')

        /** WHATWG "forbidden domain code point" (gồm C0, khoảng trắng, %, DEL). */
        private val FORBIDDEN_DOMAIN: Set<Char> = "\u0000\t\n\r #/:<>?@[\\]^|%\u007f".toSet() + (0 until 0x20).map { it.toChar() }
        private val FRAGMENT_SET = " \"<>`".toSet()
        private val QUERY_SET = " \"#<>'".toSet()
        private val PATH_SET = " \"#<>?`{}".toSet()
        private val USERINFO_SET = PATH_SET + "/:;=@[\\]^|".toSet()

        /** Host là IP (dạng đã chuẩn hóa: IPv4 có chấm hoặc IPv6 trong ngoặc vuông). */
        fun isIpHost(host: String): Boolean = IPV4_DOTTED.matches(host) || host.startsWith("[")

        /** `null` nếu URL quá dài, không phải http/https, hoặc trình duyệt sẽ từ chối nó. */
        fun parse(raw: String): Url? = try { parseOrThrow(raw) } catch (_: ParseError) { null }

        /** Scheme (chữ thường) như trình duyệt đọc, hoặc `null`. */
        fun schemeOf(raw: String): String? =
            SCHEME_RE.find(clean(raw))?.groupValues?.get(1)?.lowercase()

        private fun clean(raw: String): String =
            raw.trim { it.code <= 0x20 }.filterNot { it == '\t' || it == '\n' || it == '\r' }

        private fun parseOrThrow(raw: String): Url {
            if (raw.length > MAX_URL_LENGTH) throw ParseError("URL quá dài")
            val text = clean(raw)
            val m = SCHEME_RE.find(text) ?: throw ParseError("URL không có scheme")
            val scheme = m.groupValues[1].lowercase()
            if (scheme !in DEFAULT_PORTS) throw ParseError("Scheme không được hỗ trợ: $scheme")
            val rest = text.substring(m.range.last + 1).trimStart('/', '\\')
            val end = rest.indexOfFirst { it == '/' || it == '\\' || it == '?' || it == '#' }.let { if (it < 0) rest.length else it }
            var authority = rest.substring(0, end)
            var tail = rest.substring(end)

            var username = ""
            var password = ""
            val at = authority.lastIndexOf('@')
            if (at >= 0) {
                val userinfo = authority.substring(0, at)
                authority = authority.substring(at + 1)
                username = percentEncode(userinfo.substringBefore(':'), USERINFO_SET)
                password = if (userinfo.contains(':')) percentEncode(userinfo.substringAfter(':'), USERINFO_SET) else ""
                if (authority.isEmpty()) throw ParseError("Có thông tin đăng nhập nhưng thiếu host")
            }

            val hostText: String
            var portText: String
            if (authority.startsWith("[")) {
                val close = authority.indexOf(']')
                if (close < 0) throw ParseError("IPv6 thiếu dấu ]")
                hostText = authority.substring(0, close + 1)
                portText = authority.substring(close + 1)
                if (portText.isNotEmpty() && !portText.startsWith(":")) throw ParseError("Ký tự lạ sau IPv6")
                portText = portText.removePrefix(":")
            } else {
                hostText = authority.substringBefore(':')
                portText = if (authority.contains(':')) authority.substringAfter(':') else ""
            }

            var port: Int? = null
            if (portText.isNotEmpty()) {
                if (!portText.all { it in '0'..'9' }) throw ParseError("Cổng không hợp lệ")
                val n = portText.trimStart('0').ifEmpty { "0" }
                if (n.length > 5 || n.toInt() > 65535) throw ParseError("Cổng lớn hơn 65535")
                port = n.toInt().takeIf { it != DEFAULT_PORTS[scheme] }
            }

            val (host, kind) = parseHost(hostText)

            var fragment: String? = null
            val hash = tail.indexOf('#')
            if (hash >= 0) {
                fragment = percentEncode(tail.substring(hash + 1), FRAGMENT_SET)
                tail = tail.substring(0, hash)
            }
            var query: String? = null
            val q = tail.indexOf('?')
            if (q >= 0) {
                query = percentEncode(tail.substring(q + 1), QUERY_SET)
                tail = tail.substring(0, q)
            }
            return Url(scheme, username, password, host, kind, port, normalizePath(tail), query, fragment)
        }

        // ---- Host ---------------------------------------------------------------------------------

        private fun parseHost(text: String): Pair<String, HostKind> {
            if (text.isEmpty()) throw ParseError("URL http/https phải có host")
            if (text.startsWith("[")) {
                if (!text.endsWith("]")) throw ParseError("IPv6 thiếu dấu ]")
                return "[${parseIpv6(text.substring(1, text.length - 1))}]" to HostKind.IPV6
            }
            val decoded = String(percentDecode(text), Charsets.UTF_8)
            val ascii = domainToAscii(decoded)
            if (endsInNumber(ascii)) return parseIpv4(ascii) to HostKind.IPV4
            return ascii to HostKind.DOMAIN
        }

        /** Tên miền về ASCII như trình duyệt (xấp xỉ UTS #46 không nghiêm ngặt, giống bản Python). */
        fun domainToAscii(domain: String): String {
            val sb = StringBuilder()
            var i = 0
            while (i < domain.length) {
                val cp = domain.codePointAt(i)
                if (cp !in MAPPED_TO_NOTHING) sb.appendCodePoint(cp)
                i += Character.charCount(cp)
            }
            fun dots(s: String) = s.map { if (it in IDEOGRAPHIC_DOTS) '.' else it }.joinToString("")
            var mapped = dots(Normalizer.normalize(dots(sb.toString()), Normalizer.Form.NFKC)).lowercase()
            if (mapped.endsWith(".")) mapped = mapped.dropLast(1)
            if (mapped.isEmpty()) throw ParseError("Tên miền rỗng")
            val result = mapped.split('.').joinToString(".") { labelToAscii(it) }
            if (result.any { it in FORBIDDEN_DOMAIN }) throw ParseError("Tên miền chứa ký tự cấm")
            return result
        }

        private fun labelToAscii(label: String): String {
            if (label.all { it.code < 0x80 }) {
                val lowered = label.lowercase()
                if (lowered.startsWith("xn--")) {
                    val decoded = Punycode.decode(lowered.substring(4)) ?: throw ParseError("Nhãn punycode không hợp lệ")
                    if (decoded.isEmpty() || decoded.all { it.code < 0x80 } || decoded.codePoints().anyMatch { invalidCategory(it) }) {
                        throw ParseError("Nhãn punycode không hợp lệ")
                    }
                }
                return lowered
            }
            return "xn--" + (Punycode.encode(label) ?: throw ParseError("Không mã hóa được nhãn IDN"))
        }

        private fun invalidCategory(cp: Int): Boolean = when (Character.getType(cp).toByte()) {
            Character.CONTROL, Character.SURROGATE, Character.PRIVATE_USE, Character.UNASSIGNED -> true
            else -> false
        }

        /** Giải mã nhãn `xn--` để hiển thị; nhãn hỏng giữ nguyên. */
        fun domainToUnicode(ascii: String): String = ascii.split('.').joinToString(".") { label ->
            if (label.startsWith("xn--")) Punycode.decode(label.substring(4)) ?: label else label
        }

        /** WHATWG "ends in a number": nhãn cuối là số thập phân hoặc `0x` hex ⇒ phải đọc là IPv4. */
        private fun endsInNumber(host: String): Boolean {
            val labels = host.split('.').toMutableList()
            if (labels.last().isEmpty()) {
                if (labels.size == 1) return false
                labels.removeAt(labels.size - 1)
            }
            val last = labels.last()
            if (last.isNotEmpty() && last.all { it in '0'..'9' }) return true
            if (last.length >= 2 && last.substring(0, 2).lowercase() == "0x") return last.substring(2).all { it.isHexDigitAscii() }
            return false
        }

        private fun Char.isHexDigitAscii() = this in '0'..'9' || this in 'a'..'f' || this in 'A'..'F'

        private fun parseIpv4Number(part: String): Long {
            if (part.isEmpty()) throw ParseError("Thành phần IPv4 rỗng")
            var base = 10
            var digits = part
            if (part.length >= 2 && part.substring(0, 2).lowercase() == "0x") { base = 16; digits = part.substring(2) }
            else if (part.length >= 2 && part[0] == '0') { base = 8; digits = part.substring(1) }
            if (digits.isEmpty()) return 0
            val big = digits.toBigIntegerOrNull(base) ?: throw ParseError("Thành phần IPv4 không hợp lệ")
            if (big.signum() < 0) throw ParseError("Thành phần IPv4 không hợp lệ")
            return if (big.bitLength() > 40) Long.MAX_VALUE else big.toLong()
        }

        /** IPv4 mọi dạng trình duyệt chấp nhận (`3232235777`, `0xC0A80101`, `0300.0250.1.1`, `192.168.1`). */
        private fun parseIpv4(host: String): String {
            val parts = host.split('.').toMutableList()
            if (parts.last().isEmpty() && parts.size > 1) parts.removeAt(parts.size - 1)
            if (parts.size > 4) throw ParseError("IPv4 có quá 4 thành phần")
            val nums = parts.map(::parseIpv4Number)
            if (nums.dropLast(1).any { it > 255 }) throw ParseError("Thành phần IPv4 vượt quá 255")
            val limit = 1L shl (8 * (5 - nums.size))
            if (nums.last() >= limit) throw ParseError("Thành phần IPv4 cuối vượt giới hạn")
            var value = nums.last()
            nums.dropLast(1).forEachIndexed { i, n -> value += n shl (8 * (3 - i)) }
            return listOf(24, 16, 8, 0).joinToString(".") { ((value shr it) and 0xFF).toString() }
        }

        /** IPv6 dạng nén như `ipaddress.IPv6Address.compressed` của Python. */
        private fun parseIpv6(inner: String): String {
            if (inner.contains('%')) throw ParseError("IPv6 không được chứa zone id")
            if (inner.isEmpty() || !inner.all { it.isHexDigitAscii() || it == ':' || it == '.' } || !inner.contains(':')) {
                throw ParseError("IPv6 không hợp lệ")
            }
            val addr = try { InetAddress.getByName("[$inner]") } catch (_: Exception) { throw ParseError("IPv6 không hợp lệ") }
            val bytes = when (addr) {
                is Inet6Address -> addr.address
                is Inet4Address -> ByteArray(10) + byteArrayOf(-1, -1) + addr.address  // ::ffff:a.b.c.d
                else -> throw ParseError("IPv6 không hợp lệ")
            }
            val groups = IntArray(8) { ((bytes[2 * it].toInt() and 0xFF) shl 8) or (bytes[2 * it + 1].toInt() and 0xFF) }
            var bestStart = -1
            var bestLen = 0
            var i = 0
            while (i < 8) {
                if (groups[i] == 0) {
                    var j = i
                    while (j < 8 && groups[j] == 0) j++
                    if (j - i > bestLen) { bestStart = i; bestLen = j - i }
                    i = j
                } else i++
            }
            val hex = groups.map { it.toString(16) }
            if (bestLen < 2) return hex.joinToString(":")
            val left = hex.subList(0, bestStart).joinToString(":")
            val right = hex.subList(bestStart + bestLen, 8).joinToString(":")
            return "$left::$right"
        }

        // ---- Percent-encoding & đường dẫn -------------------------------------------------------------

        /** Percent-encode theo một tập WHATWG; giữ nguyên `%` sẵn có như trình duyệt. */
        private fun percentEncode(text: String, extra: Set<Char>): String {
            val sb = StringBuilder()
            var i = 0
            while (i < text.length) {
                val cp = text.codePointAt(i)
                val n = Character.charCount(cp)
                if (cp < 0x20 || cp > 0x7E || (n == 1 && text[i] in extra)) {
                    val bytes = String(Character.toChars(cp)).toByteArray(Charsets.UTF_8)
                    bytes.forEach { sb.append('%').append("%02X".format(it.toInt() and 0xFF)) }
                } else sb.append(text[i])
                i += n
            }
            return sb.toString()
        }

        /** `%XX` thành byte; `%` không hợp lệ giữ nguyên như WHATWG. */
        fun percentDecode(text: String): ByteArray {
            val raw = text.toByteArray(Charsets.UTF_8)
            val out = java.io.ByteArrayOutputStream(raw.size)
            var i = 0
            fun hex(b: Byte) = Character.digit(b.toInt().toChar(), 16)
            while (i < raw.size) {
                val b = raw[i]
                if (b == '%'.code.toByte() && i + 2 < raw.size && hex(raw[i + 1]) >= 0 && hex(raw[i + 2]) >= 0) {
                    out.write(hex(raw[i + 1]) * 16 + hex(raw[i + 2]))
                    i += 3
                } else {
                    out.write(b.toInt())
                    i++
                }
            }
            return out.toByteArray()
        }

        /** `\` thành `/`, xử lý `.`/`..` (cả dạng `%2e`), percent-encode. */
        private fun normalizePath(pathText: String): String {
            val text = pathText.replace('\\', '/')
            val segments = if (text.isEmpty()) emptyList() else text.split('/').drop(1)
            val out = mutableListOf<String>()
            segments.forEachIndexed { index, segment ->
                val isLast = index == segments.size - 1
                when (segment.lowercase()) {
                    "..", ".%2e", "%2e.", "%2e%2e" -> {
                        if (out.isNotEmpty()) out.removeAt(out.size - 1)
                        if (isLast) out += ""
                    }
                    ".", "%2e" -> if (isLast) out += ""
                    else -> out += percentEncode(segment, PATH_SET)
                }
            }
            return "/" + out.joinToString("/")
        }
    }
}

/** Punycode (RFC 3492), cùng hành vi với codec `punycode` của Python: chuỗi hỏng/cụt ⇒ `null`. */
object Punycode {
    private const val BASE = 36
    private const val TMIN = 1
    private const val TMAX = 26
    private const val SKEW = 38
    private const val DAMP = 700
    private const val INITIAL_BIAS = 72
    private const val INITIAL_N = 128

    private fun adapt(deltaIn: Long, numPoints: Int, first: Boolean): Int {
        var delta = if (first) deltaIn / DAMP else deltaIn / 2
        delta += delta / numPoints
        var k = 0
        while (delta > ((BASE - TMIN) * TMAX) / 2) { delta /= BASE - TMIN; k += BASE }
        return (k + (BASE - TMIN + 1) * delta / (delta + SKEW)).toInt()
    }

    private fun digitValue(c: Char): Int = when (c) {
        in 'a'..'z' -> c - 'a'
        in 'A'..'Z' -> c - 'A'
        in '0'..'9' -> c - '0' + 26
        else -> -1
    }

    private fun digitChar(d: Int): Char = if (d < 26) 'a' + d else '0' + (d - 26)

    fun decode(input: String): String? {
        val pos = input.lastIndexOf('-')
        val basic = if (pos >= 0) input.substring(0, pos) else ""
        if (basic.any { it.code >= 0x80 }) return null
        val output = basic.codePoints().toArray().toMutableList()
        val ext = if (pos >= 0) input.substring(pos + 1) else input
        var n = INITIAL_N.toLong()
        var bias = INITIAL_BIAS
        var i = 0L
        var idx = 0
        while (idx < ext.length) {
            val oldI = i
            var w = 1L
            var k = BASE
            while (true) {
                if (idx >= ext.length) return null
                val digit = digitValue(ext[idx++])
                if (digit < 0) return null
                i += digit * w
                if (i > 0x7FFFFFFFL * 64) return null
                val t = when { k <= bias -> TMIN; k >= bias + TMAX -> TMAX; else -> k - bias }
                if (digit < t) break
                w *= (BASE - t)
                k += BASE
            }
            bias = adapt(i - oldI, output.size + 1, oldI == 0L)
            n += i / (output.size + 1)
            i %= (output.size + 1)
            if (n > 0x10FFFF) return null
            output.add(i.toInt(), n.toInt())
            i++
        }
        return try {
            val sb = StringBuilder()
            output.forEach { sb.appendCodePoint(it) }
            sb.toString()
        } catch (_: Exception) { null }
    }

    fun encode(input: String): String? {
        val cps = input.codePoints().toArray()
        val out = StringBuilder()
        cps.filter { it < 0x80 }.forEach { out.append(it.toChar()) }
        val b = out.length
        var h = b
        if (b > 0) out.append('-')
        var n = INITIAL_N
        var delta = 0L
        var bias = INITIAL_BIAS
        while (h < cps.size) {
            val m = cps.filter { it >= n }.minOrNull() ?: return null
            delta += (m - n).toLong() * (h + 1)
            n = m
            for (c in cps) {
                if (c < n) delta++
                if (c == n) {
                    var q = delta
                    var k = BASE
                    while (true) {
                        val t = when { k <= bias -> TMIN; k >= bias + TMAX -> TMAX; else -> k - bias }
                        if (q < t) break
                        out.append(digitChar((t + (q - t) % (BASE - t)).toInt()))
                        q = (q - t) / (BASE - t)
                        k += BASE
                    }
                    out.append(digitChar(q.toInt()))
                    bias = adapt(delta, h + 1, h == b)
                    delta = 0
                    h++
                }
            }
            delta++
            n++
        }
        return out.toString()
    }
}
