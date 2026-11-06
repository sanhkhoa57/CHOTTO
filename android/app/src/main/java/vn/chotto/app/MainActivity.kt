package vn.chotto.app

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color as AndroidColor
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.SystemClock
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import vn.chotto.app.ui.theme.Bg
import vn.chotto.app.ui.theme.CHOTTOTheme

class MainActivity : ComponentActivity() {

    private val shield by lazy { Shield.get(this) }
    private val settings by lazy { shield.settings }
    private val logDb by lazy { LogDb(this) }

    /** Link đáng ngờ đang chờ quyết định; `null` = giao diện ứng dụng (mở từ màn hình chính). */
    private var current by mutableStateOf<LinkInspector.Result?>(null)

    /** Đang chạy Tầng 3 (tra tuổi tên miền, tối đa ~2 giây). */
    private var checking by mutableStateOf(false)
    private var isDefault by mutableStateOf(false)
    private var lang by mutableStateOf("en")

    /** Đã ghi quyết định cho link đang hiện chưa (đóng bằng Back/Home = "không mở"). */
    private var decided = false
    private var shownAt = 0L
    private var generation = 0

    override fun onResume() {
        super.onResume()
        isDefault = isDefaultBrowser(this)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        lang = settings.language
        // Lên lịch cập nhật danh sách đen hằng ngày (WorkManager nhớ lịch, KEEP nên không tạo trùng).
        Thread { BlacklistUpdater.schedule(this, settings.autoUpdate) }.start()
        if (handle(intent)) return
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.dark(AndroidColor.TRANSPARENT),
            navigationBarStyle = SystemBarStyle.dark(AndroidColor.TRANSPARENT),
        )
        setContent {
            CHOTTOTheme {
                CompositionLocalProvider(LocalLang provides lang) {
                    Box(Modifier.fillMaxSize().background(Bg).windowInsetsPadding(WindowInsets.safeDrawing)) {
                        val result = current
                        when {
                            checking -> CheckingScreen()
                            result != null -> WarningScreen(
                                result = result,
                                frictionSeconds = settings.frictionFor(result.level),
                                advice = if (settings.aiAdvice) Advisor.advise(result.signals, lang) else null,
                                onClose = { decide("cancel"); finish() },
                                onOpenAnyway = { decide("proceed"); openInRealBrowser(result.openUrl) },
                            )
                            else -> HomeApp(
                                shield = shield,
                                settings = settings,
                                logDb = logDb,
                                isDefault = isDefault,
                                onLanguage = { lang = it; settings.language = it },
                                onShareCsv = ::shareCsv,
                            )
                        }
                    }
                }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        if (isFinishing) {
            // Màn cảnh báo vừa bị đóng (Home) đang huỷ dở mà link mới đã tới: Android vẫn giao link cho Activity đang
            // huỷ, nên link sẽ mất theo. Mở một phiên mới sạch để kiểm tra link này.
            startActivity(Intent(intent).setClass(this, MainActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK))
            return
        }
        setIntent(intent)
        handle(intent)
    }

    override fun onDestroy() {
        // Màn cảnh báo bị đóng (Back, vuốt bỏ) mà chưa bấm "Vẫn mở" = không mở.
        if (isFinishing && !isChangingConfigurations) decide("cancel")
        super.onDestroy()
    }
    // KHÔNG đóng màn cảnh báo trong onStop: sau khi bấm Home, Android gọi onStop trễ ~1 giây, lúc đó link MỚI có thể
    // đã được giao vào chính Activity này; đóng ở onStop sẽ làm mất link mới. Màn cảnh báo để nguyên là an toàn
    // (quay lại vẫn phải chờ đếm ngược).

    /**
     * Thẩm định link trong `intent`. Link an toàn được chuyển ngay sang trình duyệt thật.
     * @return `true` nếu Activity đã kết thúc (không cần dựng giao diện).
     */
    private fun handle(intent: Intent?): Boolean {
        generation++
        // Intent mới thay link đang chờ quyết định: link cũ coi như không mở.
        if (current != null) decide("cancel")
        val uri = intent?.takeIf { it.action == Intent.ACTION_VIEW }?.data
        if (uri == null) {
            current = null
            checking = false
            return false
        }
        val (prelim, job) = shield.inspectFast(uri.toString())
        if (job == null) return dispatch(prelim)
        // Cần Tầng 3: tra tuổi tên miền ngoài luồng giao diện (tối đa Shield.TIER3_TIMEOUT_S giây).
        current = null
        checking = true
        val token = generation
        lifecycleScope.launch {
            val result = withContext(Dispatchers.IO) { runCatching { shield.complete(job) }.getOrDefault(prelim) }
            if (token == generation) {
                checking = false
                dispatch(result)
            }
        }
        return false
    }

    /** Link sạch: mở ngay. Đáng ngờ: hiện màn cảnh báo. @return `true` nếu đã kết thúc Activity. */
    private fun dispatch(result: LinkInspector.Result): Boolean {
        if (!result.isSuspicious) {
            if (settings.logDecisions) logDb.record(result, "auto_open", 0)
            openInRealBrowser(result.openUrl)
            return isFinishing
        }
        current = result
        decided = false
        shownAt = SystemClock.elapsedRealtime()
        return false
    }

    private fun decide(decision: String) {
        val r = current ?: return
        if (decided) return
        decided = true
        if (settings.logDecisions) logDb.record(r, decision, SystemClock.elapsedRealtime() - shownAt)
    }

    private fun t(vi: String, en: String) = if (settings.language == "vi") vi else en

    private fun shareCsv() {
        val send = Intent(Intent.ACTION_SEND).setType("text/csv")
            .putExtra(Intent.EXTRA_SUBJECT, "CHOTTO – ${t("nhật ký", "activity log")}")
            .putExtra(Intent.EXTRA_TEXT, logDb.csv())
        startActivity(Intent.createChooser(send, t("Xuất nhật ký", "Export log")))
    }

    /**
     * Anti-loop: luôn gọi đích danh một trình duyệt KHÁC CHOTTO (ưu tiên Chrome), không bao giờ gửi
     * intent "trơn" vì khi CHOTTO là trình duyệt mặc định, intent đó sẽ quay lại chính nó.
     */
    private fun openInRealBrowser(url: String) {
        val browser = findRealBrowser(this)
        if (browser == null) {
            Toast.makeText(
                this,
                t("Chưa có trình duyệt nào khác CHOTTO trên máy (ví dụ Chrome).", "No other browser than CHOTTO is installed (e.g. Chrome)."),
                Toast.LENGTH_LONG,
            ).show()
            return
        }
        val view = Intent(Intent.ACTION_VIEW, Uri.parse(url))
            .addCategory(Intent.CATEGORY_BROWSABLE)
            .setPackage(browser)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        try {
            startActivity(view)
            finish()
        } catch (_: ActivityNotFoundException) {
            Toast.makeText(this, t("Không mở được trình duyệt.", "Could not open the browser."), Toast.LENGTH_LONG).show()
        }
    }
}

private const val CHROME = "com.android.chrome"

/** Gói của trình duyệt thật để chuyển link sang: Chrome nếu có, không thì trình duyệt khác bất kỳ (trừ CHOTTO). */
fun findRealBrowser(context: Context): String? {
    val probe = Intent(Intent.ACTION_VIEW, Uri.parse("https://example.com")).addCategory(Intent.CATEGORY_BROWSABLE)
    val flags = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) PackageManager.MATCH_ALL else 0
    @Suppress("DEPRECATION")
    val packages = context.packageManager.queryIntentActivities(probe, flags)
        .map { it.activityInfo.packageName }
        .filter { it != context.packageName }
        .distinct()
    return packages.firstOrNull { it == CHROME } ?: packages.firstOrNull()
}

/** CHOTTO đang là trình duyệt mặc định? */
fun isDefaultBrowser(context: Context): Boolean {
    val probe = Intent(Intent.ACTION_VIEW, Uri.parse("https://example.com"))
    @Suppress("DEPRECATION")
    val info = context.packageManager.resolveActivity(probe, PackageManager.MATCH_DEFAULT_ONLY)
    return info?.activityInfo?.packageName == context.packageName
}
