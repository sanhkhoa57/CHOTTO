package vn.chotto.app

import android.content.Context

/**
 * Bộ thẩm định 3 tầng, cùng luồng với `chotto/engine.py`:
 * Tầng 1 danh sách đen (mọi mắt xích + URL nhúng) → Tầng 2 heuristics → Tầng 3 tuổi tên miền (chỉ khi điểm
 * Tầng 2 nằm trong khoảng `tier3_low..tier3_high`). Không phân tích được link thì cảnh báo, không bao giờ SAFE.
 */
/** Việc Tầng 3 còn dở sau [Tiers.fast]. */
class Job(val raw: String, val analysis: LinkInspector.Analysis)

/** Tầng 1 + Tầng 2 + quyết định có cần Tầng 3 (không phụ thuộc Android, chạy được trong test JVM). */
class Tiers(private val inspector: LinkInspector, private val blacklistLookup: (host: String, path: String) -> String?) {
    fun fast(raw: String, tier3Enabled: Boolean): Pair<LinkInspector.Result, Job?> {
        val rules = inspector.rules
        val original = Url.parse(raw) ?: return inspector.unparseable(raw) to null
        val a = inspector.analyze(original)

        // Tầng 1: mọi mắt xích trong chuỗi + URL nhúng.
        val toCheck = a.chain + a.chain.flatMap { inspector.embeddedUrls(it) }
        val hit = toCheck.firstOrNull { blacklistLookup(it.host, it.path) != null }
        if (hit != null) {
            val sig = LinkInspector.Signal("blacklist", 100, "Tên miền nằm trong danh sách lừa đảo đã được cộng đồng báo cáo")
            return LinkInspector.Result(
                raw, a.final.href, hit.host, inspector.registeredDomain(hit.host), 100,
                LinkInspector.Level.BLOCKED, listOf(sig), openUrl = original.href, tier = 1,
            ) to null
        }

        val eligible = tier3Enabled && !a.trusted && !a.final.isIp &&
            !rules.psl.lookup(a.final.host).isPrivate &&
            a.signals.none { it.code == "shortener" } &&
            a.score in rules.threshold("tier3_low")..rules.threshold("tier3_high")
        return inspector.toResult(raw, a) to if (eligible) Job(raw, a) else null
    }
}

class Shield private constructor(context: Context) {
    private val app = context.applicationContext
    val settings = Settings(app)
    val rules: Rules = loadRules(app)
    val inspector = LinkInspector(rules)
    val blacklist = Blacklist(app, rules)
    private val ageLookup = AgeLookup(app, rules)


    private val tiers = Tiers(inspector) { host, path -> blacklist.lookup(host, path) }

    /** Phần cục bộ (vài mili-giây): trả (kết quả sơ bộ, việc Tầng 3 hoặc `null` nếu kết quả sơ bộ là cuối cùng). */
    fun inspectFast(raw: String): Pair<LinkInspector.Result, Job?> = tiers.fast(raw, settings.tier3Enabled)

    /** Chạy Tầng 3 (có thể chặn tới `tier3_timeout` giây: gọi ngoài luồng giao diện). Không bao giờ ném lỗi. */
    fun complete(job: Job): LinkInspector.Result {
        val a = job.analysis
        val info = try { ageLookup.lookup(a.final.host, TIER3_TIMEOUT_S) } catch (_: Throwable) { null }
            ?: return inspector.toResult(job.raw, a, tier = 3)
        val impersonates = a.signals.any { it.code in setOf("combosquat", "homoglyph", "typosquat") }
        val (adjust, why) = AgeLookup.ageAdjustment(info.days, rules.ageCurve, impersonates)
        val extra = if (adjust != 0) LinkInspector.Signal("age", adjust, why) else null
        return inspector.toResult(job.raw, a, extra, tier = 3, ageDays = info.days)
    }

    /** Cả ba tầng, chặn luồng gọi (dùng cho tab "Kiểm tra"; gọi ngoài luồng giao diện). */
    fun inspect(raw: String): LinkInspector.Result {
        val (prelim, job) = inspectFast(raw)
        return if (job == null) prelim else complete(job)
    }

    /** Tải lại danh sách đen từ các nguồn. @return số mục mới, 0 nếu không thay. */
    fun updateBlacklist(log: (String) -> Unit = {}): Int = BlacklistUpdater.update(app, rules, blacklist, log)

    companion object {
        const val TIER3_TIMEOUT_S = 1.8

        @Volatile private var instance: Shield? = null

        fun get(context: Context): Shield = instance ?: synchronized(this) {
            instance ?: Shield(context).also { instance = it }
        }

        private fun loadRules(app: Context): Rules {
            fun asset(name: String) = app.assets.open(name).bufferedReader().use { it.readText() }
            return Rules.parse(asset("rules.json"), asset("popular_vn.txt"), asset("public_suffix_list.dat"))
        }
    }
}
