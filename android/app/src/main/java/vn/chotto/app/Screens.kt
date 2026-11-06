package vn.chotto.app

import android.app.role.RoleManager
import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.SystemClock
import android.provider.Settings as AndroidSettings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.compositionLocalOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import vn.chotto.app.ui.theme.Accent
import vn.chotto.app.ui.theme.AccentInk
import vn.chotto.app.ui.theme.Bg
import vn.chotto.app.ui.theme.Danger
import vn.chotto.app.ui.theme.DangerField
import vn.chotto.app.ui.theme.DangerInk
import vn.chotto.app.ui.theme.Faint
import vn.chotto.app.ui.theme.Ink
import vn.chotto.app.ui.theme.Line
import vn.chotto.app.ui.theme.Muted
import vn.chotto.app.ui.theme.Ok
import vn.chotto.app.ui.theme.Surface
import vn.chotto.app.ui.theme.Surface2
import vn.chotto.app.ui.theme.Warn
import vn.chotto.app.ui.theme.WarnField
import vn.chotto.app.ui.theme.WarnInk

/** Ngôn ngữ giao diện: "en" | "vi". */
val LocalLang = compositionLocalOf { "en" }

@Composable
fun tr(vi: String, en: String): String = if (LocalLang.current == "vi") vi else en

// ---- Thành phần dùng chung ------------------------------------------------------------------------

private class Tone(val main: Color, val ink: Color, val field: Color, val vi: String, val en: String)

private fun toneOf(level: LinkInspector.Level) = when (level) {
    LinkInspector.Level.BLOCKED -> Tone(Danger, DangerInk, DangerField, "ĐÃ CHẶN", "BLOCKED")
    LinkInspector.Level.HIGH -> Tone(Danger, DangerInk, DangerField, "NGUY CƠ CAO", "HIGH RISK")
    LinkInspector.Level.WARN -> Tone(Warn, WarnInk, WarnField, "ĐÁNG NGỜ", "SUSPICIOUS")
    LinkInspector.Level.SAFE -> Tone(Ok, Ok, Surface, "AN TOÀN", "SAFE")
}

@Composable
private fun Eyebrow(text: String, color: Color = Accent) =
    Text(text, color = color, fontSize = 12.sp, letterSpacing = 1.5.sp, fontWeight = FontWeight.SemiBold)

@Composable
private fun Card(modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    Column(
        modifier.fillMaxWidth().background(Surface, RoundedCornerShape(20.dp))
            .border(BorderStroke(1.dp, Line), RoundedCornerShape(20.dp)).padding(18.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
        content = content,
    )
}

@Composable
private fun tierText(r: LinkInspector.Result): String = when {
    r.tier == 1 -> tr("Phát hiện bởi danh sách đen (Tầng 1)", "Caught by the blacklist (Tier 1)")
    r.tier == 3 && r.ageDays != null -> tr("Phân tích heuristics + tuổi tên miền (Tầng 3)", "Heuristics + domain age (Tier 3)")
    else -> tr("Phân tích heuristics (Tầng 2)", "Heuristic analysis (Tier 2)")
}

/** Tên miền đích thật + điểm rủi ro + lý do (+ lời khuyên). Dùng cho màn cảnh báo và tab "Kiểm tra". */
@Composable
private fun ResultBody(result: LinkInspector.Result, advice: String?) {
    val t = toneOf(result.level)
    val lang = LocalLang.current
    Column(
        Modifier.fillMaxWidth().background(t.field, RoundedCornerShape(20.dp))
            .border(BorderStroke(1.dp, t.main.copy(alpha = 0.35f)), RoundedCornerShape(20.dp)).padding(18.dp),
    ) {
        Text(
            if (result.level == LinkInspector.Level.SAFE) tr("Đích đến", "Destination") else tr("Bạn sắp mở", "You are about to open"),
            color = Muted, fontSize = 12.sp,
        )
        Spacer(Modifier.height(4.dp))
        Text(
            result.displayDomain.ifEmpty { tr("(không rõ)", "(unknown)") }, color = Ink, fontSize = 24.sp,
            fontWeight = FontWeight.SemiBold, maxLines = 2, overflow = TextOverflow.Ellipsis,
        )
        if (result.host.isNotEmpty() && result.host != result.displayDomain) {
            Text(result.host, color = Faint, fontSize = 13.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        result.ageDays?.let {
            Text(
                tr("Tên miền đăng ký cách đây ${it.toInt()} ngày", "Domain registered ${it.toInt()} day(s) ago"),
                color = Muted, fontSize = 13.sp,
            )
        }
        Spacer(Modifier.height(16.dp))
        Row(verticalAlignment = Alignment.Bottom) {
            Text("${result.riskScore}", color = t.ink, fontFamily = FontFamily.Serif, fontSize = 34.sp)
            Text(
                tr(" / 100 điểm rủi ro", " / 100 risk score"), color = Muted, fontSize = 13.sp,
                modifier = Modifier.padding(bottom = 6.dp),
            )
        }
        Spacer(Modifier.height(8.dp))
        Box(Modifier.fillMaxWidth().height(4.dp).background(Line, CircleShape)) {
            Box(Modifier.fillMaxWidth(result.riskScore / 100f).height(4.dp).background(t.main, CircleShape))
        }
        Spacer(Modifier.height(10.dp))
        Text(tierText(result), color = Faint, fontSize = 12.sp)
    }
    val reasons = result.reasons(lang)
    if (reasons.isNotEmpty()) {
        Spacer(Modifier.height(24.dp))
        Eyebrow(tr("VÌ SAO CHOTTO CẢNH BÁO", "WHY CHOTTO IS WARNING YOU"))
        Spacer(Modifier.height(10.dp))
        reasons.forEach { reason ->
            Row(Modifier.padding(vertical = 6.dp)) {
                Box(Modifier.padding(top = 7.dp).size(6.dp).background(t.main, CircleShape))
                Spacer(Modifier.width(12.dp))
                Text(reason, color = Ink, fontSize = 15.sp, lineHeight = 21.sp)
            }
        }
    }
    if (advice != null) {
        Spacer(Modifier.height(20.dp))
        Card {
            Eyebrow(tr("LỜI KHUYÊN", "ADVICE"))
            Text(advice, color = Muted, fontSize = 14.sp, lineHeight = 21.sp)
        }
    }
}

// ---- Đang kiểm tra (Tầng 3) -----------------------------------------------------------------------

@Composable
fun CheckingScreen() {
    Column(Modifier.fillMaxSize(), verticalArrangement = Arrangement.Center, horizontalAlignment = Alignment.CenterHorizontally) {
        CircularProgressIndicator(color = Accent, strokeWidth = 2.dp, modifier = Modifier.size(28.dp))
        Spacer(Modifier.height(16.dp))
        Text(tr("CHOTTO đang kiểm tra link…", "CHOTTO is checking the link…"), color = Muted, fontSize = 14.sp)
    }
}

// ---- Màn hình cảnh báo "Khoan đã!" ---------------------------------------------------------------

@Composable
fun WarningScreen(
    result: LinkInspector.Result,
    frictionSeconds: Int,
    advice: String?,
    onClose: () -> Unit,
    onOpenAnyway: () -> Unit,
) {
    val t = toneOf(result.level)
    val frictionMs = frictionSeconds * 1000L
    // Đồng hồ tính bằng elapsedRealtime và kiểm lại khi bấm, không chỉ dựa vào trạng thái nút.
    val shownAt = remember(result) { SystemClock.elapsedRealtime() }
    var remaining by remember(result) { mutableIntStateOf(frictionSeconds) }
    LaunchedEffect(result) {
        while (true) {
            val left = frictionMs - (SystemClock.elapsedRealtime() - shownAt)
            remaining = ((left + 999) / 1000).toInt().coerceAtLeast(0)
            if (left <= 0) break
            delay(200)
        }
    }
    val unlocked = remaining == 0

    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 20.dp, vertical = 24.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(8.dp).background(t.main, CircleShape))
            Spacer(Modifier.width(10.dp))
            Eyebrow(tr(t.vi, t.en), t.ink)
        }
        Spacer(Modifier.height(14.dp))
        Text(tr("Khoan đã!", "Hold on!"), color = Ink, fontFamily = FontFamily.Serif, fontSize = 40.sp, lineHeight = 44.sp)
        Spacer(Modifier.height(8.dp))
        Text(
            when (result.level) {
                LinkInspector.Level.BLOCKED -> tr(
                    "Trang này nằm trong danh sách lừa đảo đã được cộng đồng báo cáo. Gần như chắc chắn là bẫy.",
                    "This page is on a community-reported scam list. It is almost certainly a trap.",
                )
                LinkInspector.Level.HIGH -> tr(
                    "Liên kết này có nhiều dấu hiệu lừa đảo. Đừng nhập mật khẩu, mã OTP hay thông tin thẻ.",
                    "This link shows many signs of a scam. Don't enter passwords, OTP codes or card details.",
                )
                else -> tr(
                    "Liên kết này có dấu hiệu bất thường. Hãy kiểm tra kỹ trước khi mở.",
                    "This link looks unusual. Check it carefully before opening.",
                )
            },
            color = Muted, fontSize = 15.sp, lineHeight = 22.sp,
        )
        Spacer(Modifier.height(24.dp))
        ResultBody(result, advice)
        Spacer(Modifier.height(32.dp))
        Button(
            onClick = onClose,
            modifier = Modifier.fillMaxWidth().height(54.dp),
            shape = RoundedCornerShape(14.dp),
            colors = ButtonDefaults.buttonColors(containerColor = Accent, contentColor = AccentInk),
        ) { Text(tr("Quay lại an toàn", "Go back to safety"), fontSize = 16.sp, fontWeight = FontWeight.SemiBold) }
        Spacer(Modifier.height(10.dp))
        OutlinedButton(
            onClick = { if (SystemClock.elapsedRealtime() - shownAt >= frictionMs) onOpenAnyway() },
            enabled = unlocked,
            modifier = Modifier.fillMaxWidth().height(50.dp),
            shape = RoundedCornerShape(14.dp),
            border = BorderStroke(1.dp, if (unlocked) Muted.copy(alpha = 0.5f) else Line),
            colors = ButtonDefaults.outlinedButtonColors(contentColor = Muted, disabledContentColor = Faint),
        ) {
            Text(
                if (unlocked) tr("Tôi hiểu rủi ro, vẫn mở", "I understand the risk, open anyway")
                else tr("Vẫn mở (chờ ${remaining}s)", "Open anyway (wait ${remaining}s)"),
                fontSize = 14.sp,
            )
        }
    }
}

// ---- Cửa sổ ứng dụng (mở từ màn hình chính) -------------------------------------------------------

private enum class Tab(val vi: String, val en: String) {
    HOME("Tổng quan", "Overview"), CHECK("Kiểm tra", "Check"), LOG("Nhật ký", "Activity"), SETTINGS("Cài đặt", "Settings")
}

@Composable
fun HomeApp(
    shield: Shield,
    settings: Settings,
    logDb: LogDb,
    isDefault: Boolean,
    onLanguage: (String) -> Unit,
    onShareCsv: () -> Unit,
) {
    var tab by remember { mutableStateOf(Tab.HOME) }
    Column(Modifier.fillMaxSize().background(Bg)) {
        Box(Modifier.weight(1f)) {
            when (tab) {
                Tab.HOME -> HomeTab(isDefault, logDb, shield)
                Tab.CHECK -> CheckTab(shield, settings)
                Tab.LOG -> LogTab(logDb, onShareCsv)
                Tab.SETTINGS -> SettingsTab(shield, settings, isDefault, onLanguage)
            }
        }
        NavigationBar(containerColor = Surface, contentColor = Ink) {
            Tab.entries.forEach { item ->
                NavigationBarItem(
                    selected = tab == item,
                    onClick = { tab = item },
                    icon = { Box(Modifier.size(8.dp).background(if (tab == item) Accent else Faint, CircleShape)) },
                    label = { Text(tr(item.vi, item.en), fontSize = 12.sp) },
                    colors = NavigationBarItemDefaults.colors(
                        selectedTextColor = Accent, unselectedTextColor = Muted, indicatorColor = Surface2,
                    ),
                )
            }
        }
    }
}

@Composable
private fun TabPage(title: String, subtitle: String, content: @Composable ColumnScope.() -> Unit) {
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 20.dp, vertical = 28.dp)) {
        Eyebrow("CHOTTO", Accent)
        Spacer(Modifier.height(12.dp))
        Text(title, color = Ink, fontFamily = FontFamily.Serif, fontSize = 32.sp, lineHeight = 38.sp)
        Spacer(Modifier.height(8.dp))
        Text(subtitle, color = Muted, fontSize = 15.sp, lineHeight = 22.sp)
        Spacer(Modifier.height(24.dp))
        Column(verticalArrangement = Arrangement.spacedBy(14.dp), content = content)
    }
}

private val timeFmt = SimpleDateFormat("dd/MM/yyyy HH:mm", Locale.getDefault())

@Composable
private fun blacklistLine(shield: Shield): String {
    val context = LocalContext.current
    val count by produceState(-1) { value = withContext(Dispatchers.IO) { shield.blacklist.count() } }
    val last = BlacklistUpdater.lastSuccess(context)
    val updated = if (last == 0L) tr("chưa cập nhật từ nguồn", "not updated from sources yet") else timeFmt.format(Date(last))
    val n = if (count < 0) "…" else "%,d".format(count)
    return tr("Danh sách đen: $n mục · $updated", "Blacklist: $n entries · $updated")
}

@Composable
private fun HomeTab(isDefault: Boolean, logDb: LogDb, shield: Shield) {
    val context = LocalContext.current
    val hasBrowser = remember { findRealBrowser(context) != null }
    val stats = remember { logDb.stats() }
    val roleLauncher = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) { }
    TabPage(
        tr("Trạm kiểm soát link", "Link checkpoint"),
        tr(
            "CHOTTO đứng giữa Zalo và trình duyệt. Link an toàn mở ngay; link đáng ngờ bị chặn lại bằng màn hình cảnh báo.",
            "CHOTTO sits between Zalo and your browser. Safe links open instantly; suspicious ones stop at a warning screen.",
        ),
    ) {
        Card {
            Eyebrow(
                if (isDefault) tr("ĐANG BẢO VỆ", "PROTECTING YOU") else tr("CHƯA BẬT BẢO VỆ", "NOT PROTECTING YET"),
                if (isDefault) Ok else WarnInk,
            )
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Stat("${stats.total}", tr("link đã kiểm", "checked"))
                Stat("${stats.warned}", tr("bị cảnh báo", "warned"))
                Stat("${stats.cancelled}", tr("đã dừng", "stopped"))
                Stat("${stats.proceeded}", tr("vẫn mở", "opened anyway"))
            }
            Text(blacklistLine(shield), color = Faint, fontSize = 12.sp)
        }
        StepCard(
            "1", tr("Đặt CHOTTO làm trình duyệt mặc định", "Make CHOTTO your default browser"),
            tr(
                "Bấm nút bên dưới và chọn CHOTTO. Nếu không thấy hộp thoại: Cài đặt › Ứng dụng › Ứng dụng mặc định › Ứng dụng trình duyệt.",
                "Tap the button below and choose CHOTTO. If no dialog appears: Settings › Apps › Default apps › Browser app.",
            ),
            isDefault,
        ) {
            if (isDefault) {
                RemoveDefaultButton()
            } else {
                Button(
                    onClick = { requestDefaultBrowser(context) { roleLauncher.launch(it) } },
                    shape = RoundedCornerShape(12.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = Accent, contentColor = AccentInk),
                ) { Text(tr("Đặt làm trình duyệt mặc định", "Set as default browser"), fontWeight = FontWeight.SemiBold) }
                TextButton(onClick = { openDefaultAppsSettings(context) }) {
                    Text(tr("Mở cài đặt ứng dụng mặc định", "Open default apps settings"), color = Accent)
                }
            }
        }
        StepCard(
            "2", tr("Bật “Mở bằng trình duyệt web” trong Zalo", "Turn on “Open in web browser” in Zalo"),
            tr(
                "Zalo › Cá nhân › Cài đặt (bánh răng) › Tin nhắn › bật “Mở bằng trình duyệt web”. " +
                    "Nếu không, Zalo tự mở link trong trình duyệt riêng và CHOTTO không kiểm tra được.",
                "Zalo › Me › Settings (gear) › Messages › turn on “Open in web browser”. " +
                    "Otherwise Zalo opens links in its own browser and CHOTTO cannot check them.",
            ),
            false,
        )
        if (!hasBrowser) {
            Text(
                tr(
                    "Chưa thấy trình duyệt nào khác trên máy. CHOTTO cần một trình duyệt thật (ví dụ Chrome) để mở link an toàn.",
                    "No other browser found. CHOTTO needs a real browser (e.g. Chrome) to open safe links.",
                ),
                color = DangerInk, fontSize = 14.sp, lineHeight = 20.sp,
            )
        }
    }
}

@Composable
private fun Stat(value: String, label: String) = Column {
    Text(value, color = Ink, fontFamily = FontFamily.Serif, fontSize = 28.sp)
    Text(label, color = Muted, fontSize = 11.sp)
}

@Composable
private fun StepCard(number: String, title: String, body: String, done: Boolean, action: (@Composable () -> Unit)? = null) {
    Card {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(
                Modifier.size(28.dp).border(BorderStroke(1.dp, if (done) Ok else Accent), CircleShape),
                contentAlignment = Alignment.Center,
            ) { Text(if (done) "✓" else number, color = if (done) Ok else Accent, fontSize = 13.sp) }
            Spacer(Modifier.width(12.dp))
            Text(title, color = Ink, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
        }
        Text(body, color = Muted, fontSize = 14.sp, lineHeight = 20.sp)
        if (done) Text(tr("Đã xong", "Done"), color = Ok, fontSize = 13.sp)
        action?.invoke()
    }
}

// ---- Tab "Kiểm tra link" ------------------------------------------------------------------------

@Composable
private fun CheckTab(shield: Shield, settings: Settings) {
    var text by remember { mutableStateOf("") }
    var result by remember { mutableStateOf<LinkInspector.Result?>(null) }
    var busy by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val lang = LocalLang.current
    TabPage(
        tr("Kiểm tra một link", "Check a link"),
        tr("Dán link bạn nhận được để xem CHOTTO đánh giá, không cần mở trang đó.", "Paste a link you received to see CHOTTO's verdict without opening the page."),
    ) {
        OutlinedTextField(
            value = text,
            onValueChange = { text = it; result = null },
            modifier = Modifier.fillMaxWidth(),
            placeholder = { Text("https://…", color = Faint) },
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
            colors = OutlinedTextFieldDefaults.colors(
                focusedTextColor = Ink, unfocusedTextColor = Ink, focusedBorderColor = Accent,
                unfocusedBorderColor = Line, cursorColor = Accent,
            ),
            shape = RoundedCornerShape(14.dp),
        )
        Button(
            onClick = {
                var s = text.trim()
                if (s.isNotEmpty() && !s.contains("://")) s = "https://$s"
                if (s.isNotEmpty()) {
                    busy = true
                    scope.launch {
                        result = withContext(Dispatchers.IO) { runCatching { shield.inspect(s) }.getOrElse { shield.inspector.unparseable(s) } }
                        busy = false
                    }
                }
            },
            enabled = text.isNotBlank() && !busy,
            modifier = Modifier.fillMaxWidth().height(50.dp),
            shape = RoundedCornerShape(14.dp),
            colors = ButtonDefaults.buttonColors(containerColor = Accent, contentColor = AccentInk),
        ) { Text(if (busy) tr("Đang kiểm tra…", "Checking…") else tr("Kiểm tra", "Check"), fontWeight = FontWeight.SemiBold) }
        result?.let { r ->
            val t = toneOf(r.level)
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(8.dp).background(t.main, CircleShape))
                Spacer(Modifier.width(10.dp))
                Eyebrow(tr(t.vi, t.en), t.ink)
            }
            Column {
                ResultBody(r, if (settings.aiAdvice && r.isSuspicious) Advisor.advise(r.signals, lang) else null)
            }
        }
    }
}

// ---- Tab "Nhật ký" ------------------------------------------------------------------------------

@Composable
private fun LogTab(logDb: LogDb, onShareCsv: () -> Unit) {
    var entries by remember { mutableStateOf(logDb.recent()) }
    val fmt = remember { SimpleDateFormat("dd/MM HH:mm", Locale.getDefault()) }
    Column(Modifier.fillMaxSize().padding(horizontal = 20.dp, vertical = 28.dp)) {
        Eyebrow("CHOTTO")
        Spacer(Modifier.height(12.dp))
        Text(tr("Nhật ký", "Activity"), color = Ink, fontFamily = FontFamily.Serif, fontSize = 32.sp)
        Spacer(Modifier.height(8.dp))
        Text(
            tr("Chỉ lưu tên miền (không đường dẫn, không mã OTP), tự xóa sau 90 ngày.", "Only the domain is stored (no path, no OTP codes), deleted after 90 days."),
            color = Muted, fontSize = 14.sp,
        )
        Row {
            TextButton(onClick = onShareCsv, enabled = entries.isNotEmpty()) { Text(tr("Xuất CSV", "Export CSV"), color = Accent) }
            TextButton(onClick = { logDb.clear(); entries = emptyList() }, enabled = entries.isNotEmpty()) {
                Text(tr("Xóa nhật ký", "Clear log"), color = DangerInk)
            }
        }
        if (entries.isEmpty()) {
            Text(tr("Chưa có link nào được kiểm tra.", "No links checked yet."), color = Faint, fontSize = 14.sp, modifier = Modifier.padding(top = 12.dp))
        }
        LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            items(entries) { e ->
                val tone = toneOf(runCatching { LinkInspector.Level.valueOf(e.level) }.getOrDefault(LinkInspector.Level.WARN))
                val decision = when (e.decision) {
                    "auto_open" -> tr("mở tự động", "opened automatically")
                    "proceed" -> tr("vẫn mở", "opened anyway")
                    "cancel" -> tr("đã dừng", "stopped")
                    else -> e.decision
                }
                Row(
                    Modifier.fillMaxWidth().background(Surface, RoundedCornerShape(14.dp)).padding(14.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Box(Modifier.size(8.dp).background(tone.main, CircleShape))
                    Spacer(Modifier.width(12.dp))
                    Column(Modifier.weight(1f)) {
                        Text(e.host.ifEmpty { tr("(không rõ)", "(unknown)") }, color = Ink, fontSize = 15.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        Text(
                            "${fmt.format(Date(e.ts))} · ${e.score} ${tr("điểm", "pts")} · $decision",
                            color = Muted, fontSize = 12.sp,
                        )
                    }
                }
            }
        }
    }
}

// ---- Tab "Cài đặt" ------------------------------------------------------------------------------

@Composable
private fun SettingsTab(shield: Shield, settings: Settings, isDefault: Boolean, onLanguage: (String) -> Unit) {
    val context = LocalContext.current
    var friction by remember { mutableIntStateOf(settings.frictionSeconds) }
    var tier3 by remember { mutableStateOf(settings.tier3Enabled) }
    var advice by remember { mutableStateOf(settings.aiAdvice) }
    var log by remember { mutableStateOf(settings.logDecisions) }
    var auto by remember { mutableStateOf(settings.autoUpdate) }
    var updating by remember { mutableStateOf(false) }
    var status by remember { mutableStateOf("") }
    val lang = LocalLang.current
    TabPage(tr("Cài đặt", "Settings"), tr("Lưu ngay khi thay đổi.", "Saved as you change them.")) {
        Card {
            Text(tr("Ngôn ngữ", "Language"), color = Ink, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                for ((code, label) in listOf("en" to "English", "vi" to "Tiếng Việt")) {
                    val selected = lang == code
                    OutlinedButton(
                        onClick = { onLanguage(code) },
                        shape = RoundedCornerShape(12.dp),
                        border = BorderStroke(1.dp, if (selected) Accent else Line),
                        colors = ButtonDefaults.outlinedButtonColors(contentColor = if (selected) Accent else Muted),
                    ) { Text(label) }
                }
            }
        }
        Card {
            Text(
                tr("Thời gian chờ nút “Vẫn mở”: $friction giây", "“Open anyway” delay: $friction s"),
                color = Ink, fontSize = 16.sp, fontWeight = FontWeight.SemiBold,
            )
            Text(
                tr("Link nguy cơ cao chờ thêm 3 giây, link trong danh sách đen thêm 5 giây.", "High-risk links wait 3 s longer, blacklisted ones 5 s longer."),
                color = Muted, fontSize = 13.sp,
            )
            Slider(
                value = friction.toFloat(),
                onValueChange = { friction = it.toInt(); settings.frictionSeconds = friction },
                valueRange = 3f..15f, steps = 11,
                colors = SliderDefaults.colors(thumbColor = Accent, activeTrackColor = Accent, inactiveTrackColor = Line),
            )
        }
        SwitchRow(
            tr("Tra tuổi tên miền (Tầng 3)", "Check domain age (Tier 3)"),
            tr(
                "Hỏi RDAP/WHOIS xem tên miền mới đăng ký chưa. Cần mạng, chỉ gửi tên miền đăng ký (không gửi đường dẫn). Tắt = hoàn toàn offline.",
                "Asks RDAP/WHOIS whether the domain is newly registered. Needs internet and sends only the registered domain (never the path). Off = fully offline.",
            ),
            tier3,
        ) { tier3 = it; settings.tier3Enabled = it }
        SwitchRow(
            tr("Lời khuyên trên màn cảnh báo", "Advice on the warning screen"),
            tr("Gợi ý xử lý theo kịch bản lừa đảo, tạo cục bộ, không gửi dữ liệu đi.", "Tips matched to the scam pattern, generated on-device, nothing is sent out."),
            advice,
        ) { advice = it; settings.aiAdvice = it }
        SwitchRow(
            tr("Ghi nhật ký", "Activity log"),
            tr("Chỉ lưu tên miền, điểm và quyết định của bạn. Tắt để không lưu gì.", "Stores only the domain, score and your decision. Turn off to store nothing."),
            log,
        ) { log = it; settings.logDecisions = it }
        SwitchRow(
            tr("Tự cập nhật danh sách đen", "Auto-update blacklist"),
            tr("Mỗi ngày một lần khi có mạng (ChongLuaDao, Phishing.Database, PhishTank).", "Once a day when online (ChongLuaDao, Phishing.Database, PhishTank)."),
            auto,
        ) {
            auto = it; settings.autoUpdate = it
            BlacklistUpdater.schedule(context, it)
        }
        val downloading = tr("Đang tải…", "Downloading…")
        val ok = tr("Đã cập nhật: %s mục", "Updated: %s entries")
        val same = tr("Không có dữ liệu mới (giữ nguyên danh sách).", "No new data (list unchanged).")
        Card {
            Text(tr("Danh sách đen", "Blacklist"), color = Ink, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
            Text(blacklistLine(shield), color = Muted, fontSize = 13.sp)
            Button(
                onClick = {
                    updating = true
                    status = downloading
                    Thread {
                        val n = runCatching { shield.updateBlacklist() }.getOrDefault(0)
                        status = if (n > 0) ok.format("%,d".format(n)) else same
                        updating = false
                    }.start()
                },
                enabled = !updating,
                shape = RoundedCornerShape(12.dp),
                colors = ButtonDefaults.buttonColors(containerColor = Accent, contentColor = AccentInk),
            ) { Text(tr("Cập nhật ngay", "Update now"), fontWeight = FontWeight.SemiBold) }
            if (status.isNotEmpty()) Text(status, color = Muted, fontSize = 13.sp)
        }
        Card {
            Text(tr("Trình duyệt mặc định", "Default browser"), color = Ink, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
            Text(
                if (isDefault) tr("CHOTTO đang là trình duyệt mặc định và kiểm tra mọi link bạn bấm.", "CHOTTO is your default browser and checks every link you tap.")
                else tr("CHOTTO chưa là trình duyệt mặc định, link không được kiểm tra.", "CHOTTO is not your default browser, links are not being checked."),
                color = Muted, fontSize = 13.sp, lineHeight = 19.sp,
            )
            if (isDefault) RemoveDefaultButton() else {
                val launcher = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) { }
                Button(
                    onClick = { requestDefaultBrowser(context) { launcher.launch(it) } },
                    shape = RoundedCornerShape(12.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = Accent, contentColor = AccentInk),
                ) { Text(tr("Đặt làm trình duyệt mặc định", "Set as default browser"), fontWeight = FontWeight.SemiBold) }
            }
        }
        Card {
            Text(tr("Về CHOTTO", "About CHOTTO"), color = Ink, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
            Text(
                tr(
                    "Bản Android dùng cùng bộ luật và cùng ba tầng thẩm định với Desktop: danh sách đen, heuristics tiếng Việt, tuổi tên miền.",
                    "The Android app uses the same rules and the same three tiers as Desktop: blacklist, Vietnamese heuristics, domain age.",
                ),
                color = Muted, fontSize = 13.sp, lineHeight = 19.sp,
            )
        }
    }
}

@Composable
private fun SwitchRow(title: String, body: String, checked: Boolean, onChange: (Boolean) -> Unit) {
    Card {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(title, color = Ink, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.height(4.dp))
                Text(body, color = Muted, fontSize = 13.sp, lineHeight = 19.sp)
            }
            Spacer(Modifier.width(12.dp))
            Switch(
                checked = checked, onCheckedChange = onChange,
                colors = SwitchDefaults.colors(checkedTrackColor = Accent, checkedThumbColor = AccentInk),
            )
        }
    }
}

// ---- Đặt / gỡ trình duyệt mặc định -----------------------------------------------------------------

/**
 * Gỡ CHOTTO khỏi vai trò trình duyệt mặc định. Android không cho app tự trao vai trò cho app khác, nên nút mở trang
 * "Ứng dụng trình duyệt" của Cài đặt (ưu tiên trang chọn trình duyệt, không có thì trang Ứng dụng mặc định) và nhắc
 * chọn lại trình duyệt cũ (ví dụ Chrome).
 */
@Composable
private fun RemoveDefaultButton() {
    val context = LocalContext.current
    val browser = remember { findRealBrowser(context)?.let { appLabel(context, it) } }
    Text(
        tr(
            "Muốn ngừng dùng CHOTTO: bấm nút bên dưới rồi chọn ${browser ?: "trình duyệt khác"} trong danh sách.",
            "To stop using CHOTTO: tap the button below and pick ${browser ?: "another browser"} in the list.",
        ),
        color = Muted, fontSize = 13.sp, lineHeight = 19.sp,
    )
    OutlinedButton(
        onClick = { openBrowserRoleSettings(context) },
        shape = RoundedCornerShape(12.dp),
        border = BorderStroke(1.dp, DangerInk.copy(alpha = 0.6f)),
        colors = ButtonDefaults.outlinedButtonColors(contentColor = DangerInk),
    ) { Text(tr("Gỡ CHOTTO khỏi trình duyệt mặc định", "Remove CHOTTO as default browser")) }
}

private fun appLabel(context: Context, pkg: String): String? = runCatching {
    val pm = context.packageManager
    pm.getApplicationLabel(pm.getApplicationInfo(pkg, 0)).toString()
}.getOrNull()

/** Trang chọn trình duyệt mặc định (Android 10+: thẳng vào mục "Ứng dụng trình duyệt"), dự phòng trang Ứng dụng mặc định. */
private fun openBrowserRoleSettings(context: Context) {
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
        try {
            context.startActivity(
                Intent("android.settings.MANAGE_DEFAULT_APP")
                    .putExtra("android.intent.extra.ROLE_NAME", RoleManager.ROLE_BROWSER)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
            )
            return
        } catch (_: Exception) { /* máy không có trang này */ }
    }
    openDefaultAppsSettings(context)
}

/**
 * Android 10+: xin vai trò trình duyệt qua RoleManager (hộp thoại hệ thống hỏi "Đặt CHOTTO làm trình duyệt mặc định?").
 * Không được thì mở thẳng trang "Ứng dụng mặc định" của Cài đặt.
 */
private fun requestDefaultBrowser(context: Context, launch: (Intent) -> Unit) {
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
        val rm = context.getSystemService(RoleManager::class.java)
        if (rm != null && rm.isRoleAvailable(RoleManager.ROLE_BROWSER) && !rm.isRoleHeld(RoleManager.ROLE_BROWSER)) {
            try {
                launch(rm.createRequestRoleIntent(RoleManager.ROLE_BROWSER))
                return
            } catch (_: ActivityNotFoundException) { /* dùng trang cài đặt */ }
        }
    }
    openDefaultAppsSettings(context)
}

private fun openDefaultAppsSettings(context: Context) {
    for (i in listOf(
        Intent(AndroidSettings.ACTION_MANAGE_DEFAULT_APPS_SETTINGS),
        Intent(AndroidSettings.ACTION_SETTINGS),
    )) {
        try {
            context.startActivity(i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            return
        } catch (_: ActivityNotFoundException) { /* thử cách tiếp theo */ }
    }
}

