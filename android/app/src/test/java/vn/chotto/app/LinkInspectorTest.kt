package vn.chotto.app

import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class LinkInspectorTest {
    private val rules: Rules by lazy {
        val a = File("src/main/assets")
        Rules.parse(File(a, "rules.json").readText(), File(a, "popular_vn.txt").readText(), File(a, "public_suffix_list.dat").readText())
    }
    private val inspector: LinkInspector by lazy { LinkInspector(rules) }

    private fun codes(url: String) = inspector.inspect(url).signals.map { it.code }

    @Test fun officialBankIsSafe() {
        val r = inspector.inspect("https://www.vietcombank.com.vn/vi-VN/KHCN")
        assertFalse(r.isSuspicious)
        assertEquals(0, r.riskScore)
    }

    @Test fun combosquatOnRiskyTld() {
        val r = inspector.inspect("https://vietcombank-xacnhan.top/dang-nhap")
        assertTrue(r.isSuspicious)
        assertTrue("combosquat" in r.signals.map { it.code })
        assertTrue("tld" in r.signals.map { it.code })
        assertEquals(LinkInspector.Level.HIGH, r.level)
    }

    @Test fun shortKeywordNeedsAffix() {
        assertTrue("combosquat" in codes("https://vcb-online.xyz/"))
        assertFalse("combosquat" in codes("https://vcbxyzabc.com/"))
    }

    @Test fun homoglyphAndTyposquat() {
        assertTrue("homoglyph" in codes("https://techc0mbank.com/"))
        assertTrue("typosquat" in codes("https://vietcombamk.com/"))
    }

    @Test fun lureKeywordInPath() {
        assertTrue("lure" in codes("https://example-shop.com/tra-cuu-phat-nguoi"))
    }

    @Test fun zaloWrapperIsUnwrapped() {
        val r = inspector.inspect("https://redirect.zalo.me/v3/verifyv2/pc?continue=https%3A%2F%2Fbidv-hotro.vip%2Fxac-minh")
        assertEquals("bidv-hotro.vip", r.host)
        assertTrue(r.isSuspicious)
        assertTrue(r.openUrl.startsWith("https://redirect.zalo.me/"))
    }

    @Test fun ipAndHttp() {
        val c = codes("http://192.168.1.10:8080/login")
        assertTrue("raw_ip" in c && "http" in c && "port" in c)
    }

    @Test fun freeHostingUsesRealPsl() {
        assertTrue("free_hosting" in codes("https://vcb-login.web.app/"))
        assertEquals("vietcombank.com.vn", rules.psl.registeredDomain("a.b.vietcombank.com.vn"))
    }

    @Test fun garbageIsNotSafe() {
        assertTrue(inspector.inspect("https://exa mple.com/").isSuspicious)
    }

    @Test fun englishReasonsAndAdvice() {
        val r = inspector.inspect("https://vietcombank-xacnhan.top/dang-nhap")
        val en = r.reasons("en")
        assertTrue(en.any { it.contains("Vietcombank") && it.contains("not the official site") })
        assertTrue(en.any { it.contains(".top ending") })
        assertTrue(Advisor.advise(r.signals, "en").contains("Zalo"))
        assertTrue(Advisor.advise(r.signals, "vi").contains("Zalo"))
    }

    @Test fun blacklistLookupMatchesHostParentsAndPaths() {
        val bl = FingerprintSet.of(
            listOf("evil.top", "scam.example.com/phish").map(FingerprintSet::fingerprint).toLongArray(),
        )
        assertNotNull(bl.lookup("login.evil.top", "/x", rules.psl))
        assertNotNull(bl.lookup("scam.example.com", "/phish/a/b", rules.psl))
        assertNull(bl.lookup("scam.example.com", "/ok", rules.psl))
        assertNull(bl.lookup("good.com", "/", rules.psl))
        assertEquals(bl.size, FingerprintSet.fromBytes(bl.toBytes())!!.size)
    }

    @Test fun blacklistEntryFormats() {
        assertEquals("evil.top" to null, BlacklistEntry.keys("||evil.top^"))
        assertEquals("evil.top" to "/a", BlacklistEntry.keys("https://evil.top/a/"))
        assertNull(BlacklistEntry.keys("# comment"))
        assertNull(BlacklistEntry.keys("localhost"))
    }

    @Test fun ageCurveAndDates() {
        val curve = rules.ageCurve
        assertEquals(50, AgeLookup.ageAdjustment(0.0, curve, false).first)
        assertEquals(0, AgeLookup.ageAdjustment(365.0, curve, false).first)
        assertEquals(0, AgeLookup.ageAdjustment(2000.0, curve, true).first)   // mạo danh: không được trừ điểm vì tuổi
        assertTrue(AgeLookup.ageAdjustment(2000.0, curve, false).first < 0)
        assertNotNull(AgeLookup.parseDate("2024-05-01T10:00:00Z"))
        assertNotNull(AgeLookup.parseDate("2024-05-01"))
        assertNotNull(AgeLookup.parseDate("01-May-2024"))
        assertNull(AgeLookup.parseDate("not a date"))
    }
}
