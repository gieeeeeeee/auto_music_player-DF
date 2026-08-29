package com.automusic.player.input

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.graphics.Path
import android.view.accessibility.AccessibilityEvent

/**
 * 无障碍手势注入服务(备用注入通道)。
 *
 * dispatchGesture 是公开 API,不受华为对 injectInputEvent 的调用方进程校验限制;
 * 多 stroke 同一手势 = 多指和弦,stroke duration = 按住时长,结束自动抬起。
 */
class AmpAccessibilityService : AccessibilityService() {

    companion object {
        @Volatile
        var instance: AmpAccessibilityService? = null
            private set

        val ready: Boolean
            get() = instance != null
    }

    override fun onServiceConnected() {
        super.onServiceConnected()
        instance = this
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {}

    override fun onInterrupt() {}

    override fun onDestroy() {
        instance = null
        super.onDestroy()
    }

    /** 一次派发和弦手势:所有手指同时按下,按住 holdMs 后自动抬起。 */
    fun chord(coords: List<Pair<Float, Float>>, holdMs: Long) {
        require(coords.isNotEmpty()) { "和弦坐标为空" }
        val builder = GestureDescription.Builder()
        for ((x, y) in coords) {
            val path = Path().apply { moveTo(x, y) }
            builder.addStroke(GestureDescription.StrokeDescription(path, 0, holdMs.coerceIn(1, 60000)))
        }
        val accepted = dispatchGesture(builder.build(), null, null)
        if (!accepted) error("dispatchGesture 被系统拒绝")
    }
}
