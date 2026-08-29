package com.automusic.player.input

import android.os.SystemClock
import android.view.InputDevice
import android.view.MotionEvent

/**
 * 多指和弦 MotionEvent 构造器。
 *
 * 按下序列:ACTION_DOWN(第1指) -> ACTION_POINTER_DOWN(依次增加第2..n指)
 * 抬起序列:ACTION_POINTER_UP(依次释放第n..2指) -> ACTION_UP(第1指)
 * 所有事件共享 downTime,属于同一手势;pointer id 0..n-1,toolType=FINGER。
 */
object MotionBuilder {

    private const val PRESSURE = 1.0f
    private const val SIZE = 1.0f

    private fun properties(count: Int): Array<MotionEvent.PointerProperties> =
        Array(count) { i ->
            MotionEvent.PointerProperties().apply {
                id = i
                toolType = MotionEvent.TOOL_TYPE_FINGER
            }
        }

    private fun coordinates(coords: List<Pair<Float, Float>>): Array<MotionEvent.PointerCoords> =
        Array(coords.size) { i ->
            MotionEvent.PointerCoords().apply {
                x = coords[i].first
                y = coords[i].second
                pressure = PRESSURE
                size = SIZE
            }
        }

    private fun obtain(
        downTime: Long,
        action: Int,
        coords: List<Pair<Float, Float>>,
    ): MotionEvent {
        val eventTime = SystemClock.uptimeMillis()
        return MotionEvent.obtain(
            downTime,
            eventTime,
            action,
            coords.size,
            properties(coords.size),
            coordinates(coords),
            0,    // metaState
            0,    // buttonState
            1f,   // xPrecision
            1f,   // yPrecision
            0,    // deviceId(虚拟输入,系统按 source 分发)
            0,    // edgeFlags
            InputDevice.SOURCE_TOUCHSCREEN,
            0,    // flags
        )
    }

    /** 和弦按下事件序列。 */
    fun chordDown(coords: List<Pair<Float, Float>>, downTime: Long): List<MotionEvent> {
        require(coords.isNotEmpty()) { "和弦坐标为空" }
        SystemClock.uptimeMillis() // 触发时钟同步
        val events = mutableListOf<MotionEvent>()
        events.add(obtain(downTime, MotionEvent.ACTION_DOWN, coords.take(1)))
        for (i in 1 until coords.size) {
            val action = MotionEvent.ACTION_POINTER_DOWN or
                (i shl MotionEvent.ACTION_POINTER_INDEX_SHIFT)
            events.add(obtain(downTime, action, coords.take(i + 1)))
        }
        return events
    }

    /** 和弦抬起事件序列。 */
    fun chordUp(coords: List<Pair<Float, Float>>, downTime: Long): List<MotionEvent> {
        require(coords.isNotEmpty()) { "和弦坐标为空" }
        val events = mutableListOf<MotionEvent>()
        for (i in coords.size - 1 downTo 1) {
            val action = MotionEvent.ACTION_POINTER_UP or
                (i shl MotionEvent.ACTION_POINTER_INDEX_SHIFT)
            events.add(obtain(downTime, action, coords.take(i + 1)))
        }
        events.add(obtain(downTime, MotionEvent.ACTION_UP, coords.take(1)))
        return events
    }

    /** 单点按下/抬起(标定测试用)。 */
    fun tapDown(x: Float, y: Float, downTime: Long): MotionEvent =
        obtain(downTime, MotionEvent.ACTION_DOWN, listOf(x to y))

    fun tapUp(x: Float, y: Float, downTime: Long): MotionEvent =
        obtain(downTime, MotionEvent.ACTION_UP, listOf(x to y))
}
