package vn.chotto.app

import java.io.File
import java.util.Random
import org.junit.Test

/** Link méo mó thế nào cũng không được làm app sập (ném exception). */
class FuzzTest {
    private val rules: Rules by lazy {
        val a = File("src/main/assets")
        Rules.parse(File(a, "rules.json").readText(), File(a, "popular_vn.txt").readText(), File(a, "public_suffix_list.dat").readText())
    }

    @Test fun neverThrows() {
        val inspector = LinkInspector(rules)
        val set = FingerprintSet.of(longArrayOf(1, 2, 3))
        val pieces = listOf(
            "http", "https", "://", "//", "@", ":", "[", "]", "%", "%zz", "%e0%a4%a", "?", "&", "=", "#", "/", "\\", ".", "..", "-", "_",
            "xn--", "xn--a", "ví-dụ", "vietcombank", "vcb", "0", "1", "99999", "65536", "-1", " ", "\n", "\u0000", "‮", "😀",
            "redirect.zalo.me", "l.facebook.com/l.php?u=", "google.com/url?q=", "aHR0cHM6Ly9ldmlsLnRvcA==", "bit.ly", "::1", "192.168.1.1",
            "com.vn", "web.app", "top", "a".repeat(300), "b".repeat(70), "href.li/", "?u=https://a.b/?u=https://c.d",
        )
        val rnd = Random(42)
        repeat(20_000) {
            val sb = StringBuilder()
            repeat(1 + rnd.nextInt(12)) { sb.append(pieces[rnd.nextInt(pieces.size)]) }
            val s = sb.toString()
            try {
                val r = inspector.inspect(s)
                r.reasons("en"); r.reasons("vi")
                Advisor.advise(r.signals, "en")
                Url.parse(s)?.let { u -> set.lookup(u.host, u.path, rules.psl); inspector.embeddedUrls(u) }
                BlacklistEntry.keys(s)
            } catch (e: Throwable) {
                throw AssertionError("Sập với đầu vào: " + s.take(120).replace("\n", "\n"), e)
            }
        }
    }
}
