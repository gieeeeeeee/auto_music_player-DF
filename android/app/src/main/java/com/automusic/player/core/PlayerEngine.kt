package com.automusic.player.core

import android.os.SystemClock
import com.automusic.player.input.TouchInjector
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/**
 * 演奏引擎:按音符序列的节奏派发触摸和弦(协程 + 绝对时钟调度,抗节奏漂移)。
 *
 * 三态控制:
 * - 开始/继续:play(startIndex) 从指定进度开始
 * - 停止:stop() 暂停演奏 -> State.Paused(done, total),进度保留
 * - 重置:reset() 进度归零 -> State.Idle,下次 play 从头开始
 *
 * 时序:每音符周期严格等于 时值 + gap;按住时长 = 时值 × hold_ratio
 * (由 TouchInjector.dispatchChord 同步完成"按下-按住-抬起")。
 */
class PlayerEngine(private val scope: kotlinx.coroutines.CoroutineScope) {

    sealed interface State {
        data object Idle : State
        data class Playing(val done: Int, val total: Int) : State
        data class Paused(val done: Int, val total: Int) : State
        data class Finished(val complete: Boolean, val error: String?) : State
    }

    private val _state = MutableStateFlow<State>(State.Idle)
    val state: StateFlow<State> = _state.asStateFlow()

    private var job: Job? = null

    @Volatile
    private var lastDone = 0

    @Volatile
    private var lastTotal = 0

    val isPlaying: Boolean
        get() = job?.isActive == true

    fun play(
        notes: List<NoteEvent>,
        bpm: Int,
        holdRatio: Double,
        gapMs: Long,
        layout: Map<String, Pair<Float, Float>>,
        screenW: Int,
        screenH: Int,
        startIndex: Int = 0,
    ) {
        if (isPlaying) return
        job = scope.launch {
            val beatMs = 60000.0 / bpm.coerceAtLeast(1)
            val total = notes.size
            lastTotal = total
            var complete = true
            var errorMsg: String? = null
            try {
                var nextStart = SystemClock.uptimeMillis()
                for (idx in startIndex.coerceIn(0, total) until total) {
                    val note = notes[idx]
                    val durMs = note.dur * beatMs
                    delayUntil(nextStart)

                    val coords = KeyPointMap.coordsFor(note.notes, layout, screenW, screenH)
                    if (coords.isNotEmpty()) {
                        // 同步完成按下-按住-抬起;结束时保证无残留按键
                        TouchInjector.dispatchChord(coords, (durMs * holdRatio).toLong())
                        nextStart += (durMs + gapMs).toLong()
                    } else {
                        // 休止符:只占时值,不加 gap(与桌面版一致)
                        nextStart += durMs.toLong()
                    }
                    lastDone = idx + 1
                    _state.value = State.Playing(lastDone, total)
                }
                // 自然演奏完成:进度归零,下次从头
                lastDone = 0
                lastTotal = 0
            } catch (e: CancellationException) {
                throw e
            } catch (e: Throwable) {
                lastDone = 0
                lastTotal = 0
                complete = false
                errorMsg = e.message ?: e.toString()
            } finally {
                // 取消(暂停/重置)时状态由 stop()/reset() 负责,这里勿覆盖
                if (kotlin.coroutines.coroutineContext.isActive) {
                    _state.value = State.Finished(complete, errorMsg)
                }
            }
        }
    }

    /** 停止(暂停):保留当前进度,之后可 play(startIndex=done) 继续或 reset() 归零。 */
    fun stop() {
        val st = _state.value
        job?.cancel()
        job = null
        _state.value = if (st is State.Playing) {
            State.Paused(lastDone, lastTotal)
        } else {
            State.Idle
        }
    }

    /** 重置:清空进度回到未开始态(仅暂停态下调用有意义)。 */
    fun reset() {
        job?.cancel()
        job = null
        lastDone = 0
        lastTotal = 0
        _state.value = State.Idle
    }

    private suspend fun delayUntil(target: Long) {
        while (kotlin.coroutines.coroutineContext.isActive) {
            val now = SystemClock.uptimeMillis()
            if (now >= target) return
            delay(target - now)
        }
    }
}
