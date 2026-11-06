package vn.chotto.app.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable

private val ChottoColors = darkColorScheme(
    primary = Accent,
    onPrimary = AccentInk,
    secondary = Warn,
    error = Danger,
    background = Bg,
    onBackground = Ink,
    surface = Surface,
    onSurface = Ink,
    surfaceVariant = Surface2,
    onSurfaceVariant = Muted,
    outline = Line,
)

/** Luôn tối, không dùng màu động của hệ thống: màn cảnh báo phải trông giống nhau trên mọi máy. */
@Composable
fun CHOTTOTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = ChottoColors, typography = Typography, content = content)
}
