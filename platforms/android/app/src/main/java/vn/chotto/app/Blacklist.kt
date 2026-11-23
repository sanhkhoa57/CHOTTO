package vn.chotto.app

import android.content.Context
import java.io.File
import java.nio.ByteBuffer
import java.security.MessageDigest

/**
 * Tầng 1: danh sách đen offline. Cùng ý tưởng với `chotto/tier1.py`: mỗi khóa (`host` hoặc `host/path`) được băm
 * còn 64 bit, mảng đã sắp xếp được tìm nhị phân, nên tra cứu chỉ chạm RAM và không lưu tên miền gốc.
 */
class FingerprintSet(private val values: LongArray) {
    val size: Int get() = values.size

    operator fun contains(key: String): Boolean = java.util.Arrays.binarySearch(values, fingerprint(key)) >= 0

    /** Khóa khớp đầu tiên với `host` (và các tên miền cha) hoặc `host` + tiền tố `path`; `null` nếu không có. */
    fun lookup(host: String, path: String, psl: Psl): String? {
        val h = host.lowercase().trimEnd('.')
        if (h.isEmpty()) return null
        val candidates = psl.parentDomains(h).toMutableList()
        var prefix = ""
        for (segment in path.lowercase().split('/').filter { it.isNotEmpty() }.take(16)) {
            prefix += "/$segment"
            candidates += h + prefix
        }
        return candidates.firstOrNull { it in this }
    }

    fun toBytes(): ByteArray {
        val buf = ByteBuffer.allocate(8 + 4 + values.size * 8)
        buf.putInt(MAGIC).putInt(VERSION)
        buf.putInt(values.size)
        values.forEach { buf.putLong(it) }
        return buf.array()
    }

    fun toArray(): LongArray = values

    companion object {
        private const val MAGIC = 0x43484650 // "CHFP"
        private const val VERSION = 1

        fun fingerprint(key: String): Long {
            val d = MessageDigest.getInstance("SHA-256").digest(key.toByteArray(Charsets.UTF_8))
            return ByteBuffer.wrap(d).long
        }

        fun of(values: LongArray): FingerprintSet {
            val sorted = values.copyOf().also { it.sort() }
            var n = 0
            for (i in sorted.indices) if (i == 0 || sorted[i] != sorted[i - 1]) sorted[n++] = sorted[i]
            return FingerprintSet(sorted.copyOf(n))
        }

        /** @return `null` nếu file cụt/sai định dạng (sẽ dựng lại từ dữ liệu khởi tạo). */
        fun fromBytes(raw: ByteArray): FingerprintSet? {
            if (raw.size < 12) return null
            val buf = ByteBuffer.wrap(raw)
            if (buf.int != MAGIC || buf.int != VERSION) return null
            val n = buf.int
            if (n < 0 || raw.size != 12 + n * 8) return null
            val v = LongArray(n) { buf.long }
            for (i in 1 until n) if (v[i] <= v[i - 1]) return null
            return FingerprintSet(v)
        }
    }
}

/** Chuẩn hóa một dòng danh sách đen thành khóa; dòng không hợp lệ trả `null`. Hỗ trợ tên miền trần, URL, `||domain^`. */
object BlacklistEntry {
    fun keys(entry: String): Pair<String, String?>? {
        var text = entry.trim()
        if (text.isEmpty() || text.startsWith("#") || text.startsWith("!") || text.startsWith("//")) return null
        if (text.startsWith("||")) text = text.substring(2).substringBefore('^').substringBefore('$')
        if (!text.contains("://")) text = "http://$text"
        val url = Url.parse(text) ?: return null
        if (!url.isIp && !url.host.contains('.')) return null
        val path = url.path.trimEnd('/').lowercase()
        return url.host to path.ifEmpty { null }
    }

    fun key(host: String, path: String?): String = if (path == null) host else host + path

    /** Tên miền tin cậy + tên miền chính thức của thương hiệu: không bao giờ được vào danh sách đen. */
    fun protectedDomains(rules: Rules): List<String> = rules.trustedDomains + rules.brands.flatMap { it.domains }

    /** Khóa hợp lệ (đã loại hậu tố công cộng và tên miền được bảo vệ: chống đầu độc dữ liệu) hoặc `null`. */
    fun acceptedKey(line: String, rules: Rules, protectedDomains: List<String>): String? {
        val (host, path) = keys(line) ?: return null
        if (!Url.isIpHost(host) && rules.psl.lookup(host).registrable == null) return null
        if (protectedDomains.any { LinkInspector.inDomain(host, it) }) return null
        return key(host, path)
    }
}

/** Danh sách đen trên đĩa (`filesDir/blacklist.fp`); tự dựng từ `blacklist.seed.txt` ở lần đầu hoặc khi file hỏng. */
class Blacklist(context: Context, private val rules: Rules) {
    private val app = context.applicationContext
    private val file = File(app.filesDir, "blacklist.fp")

    @Volatile private var set: FingerprintSet? = null

    private fun current(): FingerprintSet = set ?: synchronized(this) {
        set ?: (runCatching { FingerprintSet.fromBytes(file.readBytes()) }.getOrNull() ?: rebuildFromSeed()).also { set = it }
    }

    fun lookup(host: String, path: String): String? = current().lookup(host, path, rules.psl)

    fun count(): Int = current().size

    fun existing(): LongArray = current().toArray()

    fun seedLines(): List<String> =
        runCatching { app.assets.open("blacklist.seed.txt").bufferedReader().use { it.readLines() } }.getOrDefault(emptyList())

    private val protectedDomains: List<String> by lazy { BlacklistEntry.protectedDomains(rules) }

    fun acceptedKey(line: String): String? = BlacklistEntry.acceptedKey(line, rules, protectedDomains)

    private fun rebuildFromSeed(): FingerprintSet {
        val fps = seedLines().mapNotNull { acceptedKey(it) }.map(FingerprintSet::fingerprint).toLongArray()
        return FingerprintSet.of(fps).also { write(it) }
    }

    /** Thay toàn bộ danh sách (ghi tệp tạm rồi đổi tên: tiến trình khác không bao giờ đọc file dở). */
    fun replace(newSet: FingerprintSet) {
        write(newSet)
        set = newSet
    }

    private fun write(s: FingerprintSet) {
        val tmp = File(app.filesDir, "blacklist.fp.tmp")
        tmp.writeBytes(s.toBytes())
        if (!tmp.renameTo(file)) { file.delete(); tmp.renameTo(file) }
    }
}
