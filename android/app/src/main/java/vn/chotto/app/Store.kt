package vn.chotto.app

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper

/** Cài đặt người dùng (tương ứng `config.json` bên Desktop). */
class Settings(context: Context) {
    private val p = context.applicationContext.getSharedPreferences("chotto", Context.MODE_PRIVATE)

    var frictionSeconds: Int
        get() = p.getInt("friction_seconds", 5).coerceIn(3, 30)
        set(v) = p.edit().putInt("friction_seconds", v.coerceIn(3, 30)).apply()
    var aiAdvice: Boolean
        get() = p.getBoolean("ai_advice", true)
        set(v) = p.edit().putBoolean("ai_advice", v).apply()
    var logDecisions: Boolean
        get() = p.getBoolean("log_decisions", true)
        set(v) = p.edit().putBoolean("log_decisions", v).apply()

    /** Tầng 3: tra tuổi tên miền qua mạng. Tắt = chỉ chạy offline. */
    var tier3Enabled: Boolean
        get() = p.getBoolean("tier3_enabled", true)
        set(v) = p.edit().putBoolean("tier3_enabled", v).apply()
    /** Tự cập nhật danh sách đen mỗi ngày. */
    var autoUpdate: Boolean
        get() = p.getBoolean("auto_update", true)
        set(v) = p.edit().putBoolean("auto_update", v).apply()
    /** "en" | "vi"; mặc định theo ngôn ngữ máy. */
    var language: String
        get() = p.getString("language", null) ?: if (java.util.Locale.getDefault().language == "vi") "vi" else "en"
        set(v) = p.edit().putString("language", v).apply()

    /** WARN = cơ sở, HIGH +3 giây, BLOCKED +5 giây (giống `friction_seconds_for` của Desktop). */
    fun frictionFor(level: LinkInspector.Level): Int = frictionSeconds + when (level) {
        LinkInspector.Level.HIGH -> 3
        LinkInspector.Level.BLOCKED -> 5
        else -> 0
    }
}

/** Nhật ký cục bộ: chỉ lưu tên miền đăng ký (không đường dẫn/query), tự xóa sau 90 ngày. */
class LogDb(context: Context) : SQLiteOpenHelper(context.applicationContext, "decisions.db", null, 1) {
    data class Entry(val ts: Long, val host: String, val score: Int, val level: String, val decision: String)
    data class Stats(val total: Int, val warned: Int, val cancelled: Int, val proceeded: Int)

    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL(
            "CREATE TABLE decisions (ts INTEGER, host TEXT, score INTEGER, level TEXT, " +
                "decision TEXT, dwell_ms INTEGER, signals TEXT)",
        )
        db.execSQL("CREATE INDEX decisions_ts ON decisions(ts)")
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {}

    /** `decision`: auto_open | proceed | cancel. */
    fun record(r: LinkInspector.Result, decision: String, dwellMs: Long) {
        try {
            val now = System.currentTimeMillis()
            val db = writableDatabase
            db.insert("decisions", null, ContentValues().apply {
                put("ts", now)
                put("host", r.displayDomain)
                put("score", r.riskScore)
                put("level", r.level.name)
                put("decision", decision)
                put("dwell_ms", dwellMs)
                put("signals", r.signals.joinToString(",") { it.code })
            })
            db.delete("decisions", "ts < ?", arrayOf((now - 90L * 86_400_000).toString()))
        } catch (_: Exception) { /* nhật ký lỗi không được làm hỏng việc mở link */ }
    }

    fun recent(limit: Int = 200): List<Entry> = try {
        readableDatabase.rawQuery(
            "SELECT ts, host, score, level, decision FROM decisions ORDER BY ts DESC LIMIT ?",
            arrayOf(limit.toString()),
        ).use { c ->
            buildList { while (c.moveToNext()) add(Entry(c.getLong(0), c.getString(1), c.getInt(2), c.getString(3), c.getString(4))) }
        }
    } catch (_: Exception) { emptyList() }

    fun stats(): Stats = try {
        readableDatabase.rawQuery("SELECT level, decision FROM decisions", null).use { c ->
            var total = 0; var warned = 0; var cancel = 0; var proceed = 0
            while (c.moveToNext()) {
                total++
                if (c.getString(0) != "SAFE") warned++
                when (c.getString(1)) { "cancel" -> cancel++; "proceed" -> proceed++ }
            }
            Stats(total, warned, cancel, proceed)
        }
    } catch (_: Exception) { Stats(0, 0, 0, 0) }

    fun clear() {
        try { writableDatabase.delete("decisions", null, null) } catch (_: Exception) { }
    }

    fun csv(): String = buildString {
        append("time,domain,score,level,decision\n")
        recent(10_000).forEach { append("${java.util.Date(it.ts).toInstant()},${it.host},${it.score},${it.level},${it.decision}\n") }
    }
}
