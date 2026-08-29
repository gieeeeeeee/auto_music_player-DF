package com.automusic.player.core

import android.content.Context
import android.graphics.Rect
import android.os.Build
import android.view.WindowManager

/** 真实屏幕像素尺寸(含系统栏区域,与注入触摸坐标系一致)。 */
object ScreenMetrics {

    fun realSize(context: Context): Pair<Int, Int> {
        val wm = context.getSystemService(Context.WINDOW_SERVICE) as WindowManager
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            // 注意:必须用 maximum(整块显示器)。App 以 freeform 小窗/分屏运行时,
            // currentWindowMetrics 返回窗口边界而非屏幕,会导致坐标整体错位。
            val bounds: Rect = wm.maximumWindowMetrics.bounds
            bounds.width() to bounds.height()
        } else {
            @Suppress("DEPRECATION")
            val point = android.graphics.Point()
            @Suppress("DEPRECATION")
            wm.defaultDisplay.getRealSize(point)
            point.x to point.y
        }
    }
}
