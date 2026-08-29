package com.automusic.player.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

// 与桌面版 gui/theme.py 设计 token 对齐(暗色 + 琥珀金)
val Bg = Color(0xFF0E0E14)
val Surface1 = Color(0xFF16161E)
val Surface2 = Color(0xFF1E1E28)
val Surface3 = Color(0xFF262631)
val Ink = Color(0xFFEDEDF2)
val Ink2 = Color(0xFF9494A2)
val Ink3 = Color(0xFF5E5E6E)
val Line = Color(0xFF26262F)
val Line2 = Color(0xFF2E2E3A)
val Brand = Color(0xFFD4A24C)
val Brand2 = Color(0xFFE8B85E)
val Brand3 = Color(0xFFB88638)
val BrandSoft = Color(0x1FD4A24C)
val StateSuccess = Color(0xFF4ADE80)
val StateWarning = Color(0xFFFBBF24)
val StateError = Color(0xFFF87171)
val StateInfo = Color(0xFF38BDF8)

private val AmpColorScheme = darkColorScheme(
    primary = Brand,
    onPrimary = Bg,
    primaryContainer = Brand3,
    onPrimaryContainer = Bg,
    secondary = Brand2,
    onSecondary = Bg,
    background = Bg,
    onBackground = Ink,
    surface = Surface1,
    onSurface = Ink,
    surfaceVariant = Surface2,
    onSurfaceVariant = Ink2,
    outline = Line2,
    error = StateError,
    onError = Bg,
)

@Composable
fun AmpTheme(content: @Composable () -> Unit) {
    isSystemInDarkTheme() // App 固定暗色主题,仅保持 API 一致
    MaterialTheme(
        colorScheme = AmpColorScheme,
        content = content,
    )
}
