package dev.niels.jarvis

import android.content.Context
import android.graphics.Rect
import android.net.Uri
import android.os.SystemClock
import android.view.accessibility.AccessibilityManager
import android.view.accessibility.AccessibilityNodeInfo
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.runtime.withFrameMillis
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.isSpecified
import androidx.compose.ui.geometry.Rect as ComposeRect
import androidx.compose.ui.layout.LayoutCoordinates
import androidx.compose.ui.layout.positionOnScreen
import androidx.compose.ui.platform.LocalView
import java.io.IOException
import java.time.Instant
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.withContext
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import org.json.JSONException
import org.json.JSONObject

internal data class ChatStamp(val id: String, val at: Instant) : Comparable<ChatStamp> {
    override fun compareTo(other: ChatStamp) = compareValuesBy(this, other, ChatStamp::at, ChatStamp::id)
}

internal class ChatMessage(val json: JSONObject) {
    val stamp = ChatStamp(json.getString("id"), Instant.parse(json.getString("at")))
    val id get() = stamp.id
    private val source = json.getString("source")
    val owner = json.getString("role") == "owner"
    val tracked = json.getString("role") == "assistant" && source != "native_progress"
    val terminal = source == "native_final" || source == "native_failure"
}

internal class ChatShown(context: Context) {
    private val preferences = context.getSharedPreferences("chat-shown", Context.MODE_PRIVATE)
    private val enrolled = preferences.getString("enrolled", null)?.let(Instant::parse)
        ?: Instant.ofEpochMilli(context.packageManager.getPackageInfo(context.packageName, 0).lastUpdateTime).also {
            preferences.edit().putString("enrolled", it.toString()).apply()
        }
    private data class Receipts(val start: Instant, val cleared: Instant?, val ids: Map<String, Instant>)

    private var receipts by mutableStateOf(Receipts(
        preferences.getString("start", null)?.let(Instant::parse) ?: enrolled,
        preferences.getString("cleared", null)?.let(Instant::parse),
        preferences.getStringSet("ids", emptySet()).orEmpty().associate { entry ->
            entry.substringAfter(' ') to Instant.parse(entry.substringBefore(' '))
        },
    ))

    val start get() = receipts.start
    fun isNew(stamp: ChatStamp): Boolean = receipts.let { stamp.at > it.start && stamp.id !in it.ids }
    fun recorded(id: String): Boolean = id in receipts.ids
    fun recorded(stamp: ChatStamp): Boolean = receipts.let {
        stamp.id in it.ids || (stamp.at > enrolled && it.cleared?.let { through -> stamp.at <= through } == true)
    }

    @Synchronized
    fun record(messages: List<ChatStamp>): Boolean {
        val ids = receipts.ids + messages.filter { it.at > start }.associate { it.id to it.at }
        val dropped = ids.entries.sortedBy { it.value }.dropLast(2_000)
        return save(dropped.lastOrNull()?.value ?: start, receipts.cleared, ids)
    }

    @Synchronized
    fun clear(through: ChatStamp) = save(maxOf(start, through.at), maxOf(receipts.cleared ?: enrolled, through.at), receipts.ids)

    private fun save(start: Instant, cleared: Instant?, ids: Map<String, Instant>): Boolean {
        val next = Receipts(start, cleared, ids.filterValues { it > start })
        if (next == receipts) return true
        val saved = preferences.edit()
            .putString("enrolled", enrolled.toString())
            .putString("start", next.start.toString())
            .putString("cleared", next.cleared?.toString())
            .putStringSet("ids", next.ids.mapTo(mutableSetOf()) { (id, at) -> "$at $id" })
            .commit()
        if (saved) receipts = next
        return saved
    }
}

internal class ChatPage(page: JSONObject) {
    val messages = page.objects("items").map(::ChatMessage)
    val before = page.string("next_before")
    val owed = page.getJSONArray("owed").let { ids -> List(ids.length(), ids::getString) }
}

internal suspend fun readChatPage(
    api: HomeApi, notices: PhoneNotices, before: String?, timeoutMillis: Long?,
    confirm: suspend () -> Boolean,
): ChatPage {
    val active = notices.snapshot()
    val path = "/api/messages" + (before?.let { "?before=${Uri.encode(it)}" } ?: "")
    return ChatPage(api.read(path, timeoutMillis) ?: throw IOException("conversation unavailable")).also {
        if (!confirm()) throw ChatPageDeferred()
        notices.sweep(active, it)
    }
}

internal class ChatPageDeferred : IOException()

internal data class ChatRead(val finals: List<String>, val arrivals: Set<String>)

internal class ChatHistory(private val shown: ChatShown) {
    private val reads = Mutex()
    private val receiptAuthority = Mutex()
    private var onReceipt: (() -> Unit)? = null
    private var outside by mutableStateOf(emptyList<ChatStamp>())
    private val learned = mutableMapOf<String, Long>()
    private val timings = mutableMapOf<String, Dwell>()
    private val observations = mutableStateMapOf<String, ChatStamp>()
    val reportPending get() = observations.values.any(::canRecord)
    val latest = ReadState<ChatRead>()
    var authorizationEpoch by mutableIntStateOf(0)
        private set
    var writeProblem by mutableStateOf<String?>(null)
        private set
    private var lastFrame = 0L
    private var absentAt: Long? = null
    private var awayFrom: Instant? = null
    private var awayThrough: Instant? = null

    var rows by mutableStateOf(emptyList<ChatMessage>())
        private set
    var crossing by mutableIntStateOf(0)
        private set
    var owed by mutableStateOf(emptyList<String>())
        private set
    var before by mutableStateOf<String?>(null)
        private set
    private var received = false
    var attending by mutableStateOf(false)
        private set
    var visit by mutableIntStateOf(0)
        private set
    var placedVisit by mutableIntStateOf(-1)
        private set
    var boundary by mutableStateOf<String?>(null)
        private set
    val marked = mutableStateMapOf<String, Unit>()

    data class Clear(val through: ChatStamp, val count: Int, val deadline: Long)
    var pendingClear by mutableStateOf<Clear?>(null)
        private set

    val newAbove get() = outside.count(::isNew)
    val nearestOlder get() = outside.asSequence().filter(::isNew).maxOrNull()
    val newTotal get() = newAbove + rows.count(::isNew)

    fun isNew(message: ChatMessage) = message.tracked && isNew(message.stamp)
    private fun isNew(stamp: ChatStamp) =
        canRecord(stamp) && (stamp.id !in observations || writeProblem != null)

    private fun canRecord(stamp: ChatStamp) =
        (pendingClear?.through?.at?.let { stamp.at > it } ?: true) && shown.isNew(stamp)

    fun learnedAt(id: String) = learned.getOrPut(id, SystemClock::elapsedRealtime)

    fun observeReceipt(observer: () -> Unit): () -> Unit {
        onReceipt = observer
        return { if (onReceipt === observer) onReceipt = null }
    }

    fun accept(row: ChatMessage) {
        rows = mergeRows(rows, listOf(row))
        crossing++
    }

    fun notifyReceipt() { onReceipt?.invoke() }

    suspend fun admitReceipt(epoch: Int, settle: suspend () -> Unit): Boolean = receiptAuthority.withLock {
        if (epoch != authorizationEpoch) return false
        settle()
        true
    }

    private fun mergeRows(older: List<ChatMessage>, newer: List<ChatMessage>) =
        (older + newer).associateBy(ChatMessage::id).values.sortedBy(ChatMessage::stamp)

    private fun insertionsSince(previous: List<ChatMessage>): List<ChatMessage> {
        if (rows === previous) return emptyList()
        val known = previous.mapTo(mutableSetOf(), ChatMessage::id)
        return rows.filter { it.id !in known }
    }

    fun attend(value: Boolean) {
        if (value == attending) return
        val now = SystemClock.elapsedRealtime()
        attending = value
        lastFrame = 0
        if (!value) {
            absentAt = now
            awayFrom = Instant.now()
            awayThrough = null
            timings.values.forEach { it.accessible = 0 }
        } else {
            awayThrough = Instant.now()
            if (absentAt?.let { now - it >= 300_000 } == true) {
                visit++
                boundary = null
                marked.clear()
                timings.clear()
            }
        }
    }

    fun arrivedAway(message: ChatMessage): Boolean =
        !attending || (awayFrom?.let { message.stamp.at >= it } == true &&
            awayThrough?.let { message.stamp.at <= it } == true)

    suspend fun refresh(revisit: Boolean, recheckRetained: Boolean, page: suspend (String?) -> ChatPage) = reads.withLock {
        applyRead {
            val knownProjection = received
            val initial = !knownProjection || rows.isEmpty()
            val previous = rows
            val retainedEdge = previous.firstOrNull()?.stamp
            val reloadRetained = revisit || recheckRetained
            val scanEdge = if (reloadRetained) retainedEdge else previous.lastOrNull()?.stamp
            val head = page(null)
            val retained = mutableListOf<ChatPage>()
            val oldMarks = mutableListOf<ChatStamp>()
            var current = head
            var keep = true
            var count = initial || revisit
            while (true) {
                if (keep) retained.add(current)
                if (count) oldMarks += current.messages.filter { it.tracked && shown.isNew(it.stamp) }.map { it.stamp }
                val cursor = current.before ?: break
                val first = current.messages.firstOrNull()?.stamp ?: throw IOException("invalid message page")
                count = count && first.at > shown.start
                keep = if (initial) retained.size < 3 && count else scanEdge != null && first > scanEdge
                if (!count && !keep) break
                current = page(cursor)
            }

            val kept = if (initial) {
                val limit = when {
                    oldMarks.any { mark -> retained.last().messages.firstOrNull()?.stamp?.let { mark < it } == true } -> retained.lastIndex
                    else -> retained.indexOfLast { candidate -> candidate.messages.any(::isNew) }.coerceAtLeast(0)
                }
                val preceding = retained[limit].messages.firstOrNull()?.let(::isNew) == true
                retained.take(limit + if (preceding) 2 else 1)
            } else retained

            val updated = kept.asReversed().flatMap { it.messages }
            if (initial) before = kept.last().before
            val projected = when {
                initial -> updated
                reloadRetained -> updated.filter { retainedEdge == null || it.stamp >= retainedEdge }
                else -> mergeRows(previous, updated)
            }
            rows = mergeRows(projected, insertionsSince(previous))
            rows.forEach { learnedAt(it.id) }
            val oldest = rows.firstOrNull()?.stamp
            if (initial || revisit) outside = oldMarks.filter { oldest != null && it < oldest }
            owed = current.owed
            if (placedVisit != visit) {
                boundary = rows.firstOrNull(::isNew)?.id
                placedVisit = visit
            }
            received = true
            val terminals = rows.filter { it.terminal }
            val known = previous.mapTo(mutableSetOf()) { it.id }
            val arrivals = terminals.filter {
                knownProjection && (retainedEdge == null || it.stamp >= retainedEdge) && it.id !in known
            }
            ChatRead(terminals.map { it.id }, arrivals.mapTo(mutableSetOf()) { it.id })
        }
    }

    suspend fun rejectAccess(error: IOException) = reads.withLock {
        loseAuthority(error)
    }

    suspend fun earlier(page: suspend (String?) -> ChatPage) = reads.withLock {
        val cursor = before ?: return@withLock
        applyRead {
            val older = page(cursor)
            rows = mergeRows(older.messages, rows)
            older.messages.forEach { learnedAt(it.id) }
            before = older.before
            outside = outside.filter { stamp -> stamp < (rows.firstOrNull()?.stamp ?: stamp) }
            owed = older.owed
            latest.data
        }
    }

    private suspend fun applyRead(read: suspend () -> ChatRead?): Boolean = try {
        val result = read()
        latest.refresh { result }
    } catch (error: SignInRequired) {
        loseAuthority(error)
    } catch (error: ViewerUpdateRequired) {
        loseAuthority(error)
    } catch (error: IOException) {
        latest.refresh { throw error }
    } catch (error: JSONException) {
        latest.refresh { throw error }
    }

    private suspend fun loseAuthority(error: IOException): Boolean = receiptAuthority.withLock {
        val newLoss = !latest.authorityLost || received || rows.isNotEmpty()
        latest.refresh { throw error }
        if (newLoss) {
            rows = emptyList()
            owed = emptyList()
            outside = emptyList()
            before = null
            received = false
            boundary = null
            placedVisit = -1
            learned.clear()
            marked.clear()
            timings.clear()
            authorizationEpoch++
        }
        false
    }

    fun clear(through: ChatStamp) {
        if (pendingClear != null) return
        val count = newAbove + rows.count { it.stamp <= through && isNew(it) }
        pendingClear = Clear(through, count, SystemClock.elapsedRealtime() + 5_000)
    }

    fun undo() { pendingClear = null }

    fun finishClear() {
        val clear = pendingClear ?: return
        val saved = shown.clear(clear.through)
        writeProblem = if (saved) null else "could not save shown messages"
        if (saved) {
            observations.entries.removeAll { !shown.isNew(it.value) }
        }
        pendingClear = null
    }

    fun record(messages: List<ChatMessage>) {
        if (attending) messages.filter(::isNew).forEach { observations[it.id] = it.stamp }
    }

    suspend fun flushObserved() {
        val batch = observations.values.filter(::canRecord)
        if (batch.isEmpty()) return
        withContext(NonCancellable) {
            completeReport(batch, withContext(Dispatchers.IO) { shown.record(batch) })
        }
    }

    fun flushBeforeLeaving() {
        val batch = observations.values.filter(::canRecord)
        if (batch.isNotEmpty()) completeReport(batch, shown.record(batch))
    }

    private fun completeReport(batch: List<ChatStamp>, saved: Boolean) {
        writeProblem = if (saved) null else "could not save shown messages"
        if (saved) {
            for (stamp in batch) observations.remove(stamp.id)
        }
    }

    private data class Dwell(var head: Long = 0, var tail: Long = 0, var accessible: Long = 0, var last: Int = 0)

    fun sample(frame: Long, samples: Map<ChatMessage, Int>) {
        val elapsed = (frame - lastFrame).takeIf { lastFrame != 0L && it in 0..100 } ?: 0L
        lastFrame = frame
        val active = samples.keys.mapTo(mutableSetOf()) { it.id }
        for ((id, time) in timings) if (id !in active) {
            time.last = 0
            time.accessible = 0
        }
        val done = mutableListOf<ChatMessage>()
        for ((message, visible) in samples) {
            val time = timings.getOrPut(message.id, ::Dwell)
            val continuous = visible and time.last
            if (continuous and 1 != 0) time.head += elapsed
            if (continuous and 2 != 0) time.tail += elapsed
            if (visible and 4 == 0) time.accessible = 0
            else if (continuous and 4 != 0) time.accessible += elapsed
            time.last = visible
            if ((time.head >= 1_000 && time.tail >= 1_000) || time.accessible >= 1_000) done += message
        }
        record(done)
        done.forEach { timings.remove(it.id) }
    }

    fun stopSampling() {
        lastFrame = 0
        timings.values.forEach {
            it.last = 0
            it.accessible = 0
        }
    }
}

internal class ChatViewport {
    var viewport: LayoutCoordinates? = null
    val cards = mutableMapOf<String, Pair<ChatMessage, LayoutCoordinates>>()

    @Composable
    fun Observe(history: ChatHistory, line: Float, hasNew: Boolean, excludedId: String? = null) {
        val view = LocalView.current
        val accessibility = view.context.getSystemService(AccessibilityManager::class.java)
        LaunchedEffect(this, history.attending, hasNew, line, excludedId) {
            if (!history.attending || !hasNew) return@LaunchedEffect
            try {
                while (true) withFrameMillis { now ->
                    val inner = viewport?.screenRect()
                    val candidates = if (inner == null) emptyList() else cards.values.filter {
                        it.first.id != excludedId && history.isNew(it.first)
                    }
                    val focus = if (candidates.isEmpty() || !accessibility.isEnabled) null else {
                        view.accessibilityNodeProvider?.findFocus(AccessibilityNodeInfo.FOCUS_ACCESSIBILITY)?.let { node ->
                            Rect().also(node::getBoundsInScreen)
                        }
                    }
                    val location = focus?.takeUnless(Rect::isEmpty)?.let { Offset(it.exactCenterX(), it.exactCenterY()) }
                    val samples = buildMap {
                        if (inner != null) for ((message, coordinates) in candidates) {
                            val box = coordinates.screenRect() ?: continue
                            val height = line.coerceAtMost(box.height)
                            var visible = 0
                            if (box.top >= inner.top && box.top + height <= inner.bottom) visible = 1
                            if (box.bottom <= inner.bottom && box.bottom - height >= inner.top) visible = visible or 2
                            if (location != null && inner.contains(location) && box.contains(location)) visible = visible or 4
                            if (visible != 0) put(message, visible)
                        }
                    }
                    history.sample(now, samples)
                }
            } finally {
                history.stopSampling()
            }
        }
    }

    private fun LayoutCoordinates.screenRect(): ComposeRect? {
        if (!isAttached) return null
        val start = positionOnScreen()
        if (!start.isSpecified) return null
        return ComposeRect(start.x, start.y, start.x + size.width, start.y + size.height)
    }
}
