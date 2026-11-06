package vn.chotto.app

import java.io.File
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * Bản Android phải cho CÙNG kết quả với Desktop (Python) và tiện ích (JS) trên bộ test dùng chung
 * `tests/data/engine_vectors.json` (Tầng 3 tắt, Tầng 1 dùng danh sách đen khởi tạo). Sinh lại vector bằng
 * `python tools/gen_engine_vectors.py` khi đổi luật.
 */
class ParityTest {
    private val rules: Rules by lazy {
        val a = File("src/main/assets")
        Rules.parse(File(a, "rules.json").readText(), File(a, "popular_vn.txt").readText(), File(a, "public_suffix_list.dat").readText())
    }

    @Test fun matchesDesktopVectors() {
        val inspector = LinkInspector(rules)
        val protectedDomains = BlacklistEntry.protectedDomains(rules)
        val seed = File("src/main/assets/blacklist.seed.txt").readLines()
            .mapNotNull { BlacklistEntry.acceptedKey(it, rules, protectedDomains) }
        val blacklist = FingerprintSet.of(seed.map(FingerprintSet::fingerprint).toLongArray())
        val tiers = Tiers(inspector) { host, path -> blacklist.lookup(host, path, rules.psl) }

        val vectors = JSONObject(File("../../tests/data/engine_vectors.json").readText()).getJSONArray("vectors")
        val problems = mutableListOf<String>()
        for (i in 0 until vectors.length()) {
            val v = vectors.getJSONObject(i)
            val url = v.getString("url")
            val r = try { tiers.fast(url, tier3Enabled = false).first } catch (e: Throwable) {
                problems += "$url\n    CRASH $e"; continue
            }
            val tier = if (r.signals.any { it.code == "unparseable" }) 0 else r.tier
            val expectedSignals = v.getJSONArray("signals").let { a ->
                List(a.length()) { a.getJSONArray(it).let { s -> "${s.getString(0)}:${s.getInt(1)}:${s.getString(2)}" } }
            }
            val actualSignals = r.signals.sortedByDescending { it.points }.map { "${it.code}:${it.points}:${it.brand}" }
            val expectedReasons = v.getJSONArray("reasons").let { a -> List(a.length()) { a.getString(it) } }
            val advice = if (r.level != LinkInspector.Level.SAFE) Advisor.advise(r.signals, "vi") else ""
            val diffs = buildList {
                if (r.riskScore != v.getInt("score")) add("score ${r.riskScore} != ${v.getInt("score")}")
                if (r.level.name != v.getString("level")) add("level ${r.level} != ${v.getString("level")}")
                if (tier != v.getInt("tier")) add("tier $tier != ${v.getInt("tier")}")
                if (r.host != v.getString("host")) add("host '${r.host}' != '${v.getString("host")}'")
                if (r.displayDomain != v.getString("display_domain")) add("display '${r.displayDomain}' != '${v.getString("display_domain")}'")
                if (actualSignals != expectedSignals) add("signals $actualSignals != $expectedSignals")
                if (r.reasons("vi") != expectedReasons) add("reasons ${r.reasons("vi")} != $expectedReasons")
                if (advice != v.getString("advice")) add("advice khác")
            }
            if (diffs.isNotEmpty()) problems += url.take(150) + "\n    " + diffs.joinToString("\n    ")
        }
        File("build/parity-report.txt").writeText("${problems.size}/${vectors.length()} lệch\n\n" + problems.joinToString("\n"))
        assertEquals("${problems.size} vector lệch, xem app/build/parity-report.txt\n" + problems.take(15).joinToString("\n"), 0, problems.size)
    }

    /** Bộ đọc URL phải cho cùng host/href với trình duyệt (`tests/data/url_vectors.json`, sinh từ Chrome). */
    @Test fun urlParserMatchesBrowserVectors() {
        val vectors = JSONObject(File("../../tests/data/url_vectors.json").readText()).getJSONArray("vectors")
        val problems = mutableListOf<String>()
        for (i in 0 until vectors.length()) {
            val v = vectors.getJSONObject(i)
            val input = v.getString("input")
            val u = Url.parse(input)
            if (!v.getBoolean("valid")) {
                if (u != null) problems += "$input: phải từ chối, lại đọc được ${u.href}"
                continue
            }
            if (u == null) { problems += "$input: phải đọc được"; continue }
            if (u.host != v.getString("host")) problems += "$input: host ${u.host} != ${v.getString("host")}"
            if (u.href != v.getString("href")) problems += "$input: href ${u.href} != ${v.getString("href")}"
        }
        assertEquals(problems.joinToString("\n"), 0, problems.size)
    }
}
