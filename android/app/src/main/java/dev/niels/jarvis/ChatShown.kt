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
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject

internal data class ChatStamp(val id: String, val at: Instant) : Comparable<ChatStamp> {
    override fun compareTo(other: ChatStamp) = compareValuesBy(this, other, ChatStamp::at, ChatStamp::id)
}

internal class ChatMessage(val json: JSONObject) {
    val stamp = ChatStamp(json.getString("id"), Instant.parse(json.getString("at")))
    val id get() = stamp.id
    private val source = json.getString("source")
    val tracked = json.getString("role") == "assistant" && source != "native_progress"
    val terminal = source == "native_final" || source == "native_failure"
}

internal class ShownReports private constructor(context: Context) {
    private enum class State { PENDING, ACKNOWLEDGED, DROPPED }

    private val api = HomeApi(context)
    private val notices = PhoneNotices.get(context)
    private val writes = Mutex()
    private val reports = mutableStateMapOf<String, State>()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private var authority = 0L
    private var retry: Job? = null
    var problem by mutableStateOf<String?>(null)
        private set

    fun hides(id: String): Boolean = reports[id] == State.ACKNOWLEDGED ||
        (reports[id] == State.PENDING && problem == null)
    fun contains(id: String) = id in reports

    fun record(id: String) {
        if (id in reports) return
        reports[id] = State.PENDING
        if (retry?.isActive == true) return
        retry = scope.launch {
            do {
                delay(1_000)
                flush()
            } while (State.PENDING in reports.values)
        }
    }

    fun confirmed(ids: Collection<String>) {
        for (id in ids) reports.remove(id)
        if (State.PENDING !in reports.values) problem = null
    }

    fun startVisit() { reports.entries.removeAll { it.value == State.DROPPED } }

    fun reset() {
        authority++
        reports.clear()
        problem = null
    }

    fun launch(run: suspend () -> Unit) = scope.launch { run() }

    suspend fun flush() = withContext(Dispatchers.Main.immediate) {
        writes.withLock {
            while (true) {
                val ids = reports.asSequence().filter { it.value == State.PENDING }.map { it.key }.take(200).toList()
                if (ids.isEmpty()) return@withLock
                val revision = notices.revisionBeforeWrite()
                val writingUnder = authority
                val acknowledged = try {
                    api.writeShown("/api/shown", JSONObject().put("ids", JSONArray(ids)))
                    true
                } catch (_: SignInRequired) {
                    // The API already refreshed once. Reports must not prompt sign-in.
                    false
                } catch (_: ViewerUpdateRequired) {
                    false
                } catch (_: IOException) {
                    if (writingUnder == authority) problem = "could not save shown messages"
                    return@withLock
                }
                if (writingUnder != authority) return@withLock
                val outcome = if (acknowledged) State.ACKNOWLEDGED else State.DROPPED
                ids.filter { it in reports }.forEach { reports[it] = outcome }
                problem = null
                if (!acknowledged) return@withLock
                notices.confirmHeld(revision, ids)
            }
        }
    }

    companion object {
        @Volatile private var instance: ShownReports? = null

        fun get(context: Context): ShownReports = instance ?: synchronized(this) {
            instance ?: ShownReports(context.applicationContext).also { instance = it }
        }
    }
}

internal class ChatPage(page: JSONObject) {
    val messages = page.objects("items").map(::ChatMessage)
    val before = page.string("next_before")
    val new = page.ids("new").toSet()
    val newTotal = page.count("new_total")
    val owed = page.ids("owed")

    init {
        if (new.size > newTotal || !messages.filter { it.tracked }.map { it.id }.containsAll(new) ||
            owed.size != page.count("owed_total")
        ) throw IOException("invalid shown state")
    }

    private fun JSONObject.ids(key: String): List<String> = getJSONArray(key).let { array ->
        List(array.length(), array::getString).also { ids ->
            if (!ids.all(::canonicalUuid) || ids.toSet().size != ids.size) throw IOException("invalid message ids")
        }
    }

    private fun JSONObject.count(key: String): Int =
        (get(key) as? Int)?.takeIf { it >= 0 } ?: throw IOException("invalid message count")
}

internal suspend fun readChatPage(
    api: HomeApi, notices: PhoneNotices, before: String?, timeoutMillis: Long? = null,
): ChatPage {
    val active = notices.snapshot()
    val path = "/api/messages" + (before?.let { "?before=${Uri.encode(it)}" } ?: "")
    return ChatPage(api.read(path, timeoutMillis) ?: throw IOException("conversation unavailable")).also {
        notices.sweep(active, it)
    }
}

internal data class ChatRead(val finals: List<String>, val arrivals: Set<String>)

internal class ChatHistory(
    private val api: HomeApi,
    private val reports: ShownReports,
    private val notices: PhoneNotices,
) {
    private val reads = Mutex()
    private val clearing = Mutex()
    private var newIds by mutableStateOf(emptySet<String>())
    private var serverTotal by mutableIntStateOf(0)
    private val learned = mutableMapOf<String, Long>()
    private val timings = mutableMapOf<String, Dwell>()
    val latest = ReadState<ChatRead>()
    var authorizationEpoch by mutableIntStateOf(0)
        private set
    private var clearProblem by mutableStateOf<String?>(null)
    private var awaitingClearRead by mutableStateOf(false)
    val writeProblem get() = clearProblem ?: reports.problem
    private var lastFrame = 0L
    private var absentAt: Long? = null
    private var awayFrom: Instant? = null
    private var awayThrough: Instant? = null

    var rows by mutableStateOf(emptyList<ChatMessage>())
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

    data class Clear(val through: ChatStamp, val count: Int, val deadline: Long, val sending: Boolean = false)
    var pendingClear by mutableStateOf<Clear?>(null)
        private set

    val newAbove get() = if (pendingClear == null && !awaitingClearRead) (serverTotal - newIds.size).coerceAtLeast(0) else 0
    val newTotal get() = newAbove + rows.count(::isNew)

    fun isNew(message: ChatMessage) = message.id in newIds && !reports.hides(message.id) &&
        (pendingClear?.let { message.stamp > it.through } != false)

    fun canObserve(message: ChatMessage, detached: Boolean): Boolean =
        message.tracked && !reports.contains(message.id) &&
            (isNew(message) || (detached && rows.none { it.id == message.id }))

    fun learnedAt(id: String) = learned.getOrPut(id, SystemClock::elapsedRealtime)

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
                reports.startVisit()
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
            val head = page(null)
            val headIds = head.messages.map { it.id }
            val reloadRetained = revisit || recheckRetained ||
                head.newTotal < (newIds - headIds.toSet() + head.new).size
            val scanEdge = if (reloadRetained) retainedEdge else previous.lastOrNull()?.stamp
            val retained = mutableListOf(head)
            var current = head
            var loadedNew = head.new.size
            while (true) {
                val cursor = current.before ?: break
                val first = current.messages.firstOrNull() ?: throw IOException("invalid message page")
                val keep = if (initial) {
                    retained.size < 3 &&
                        (current.newTotal > loadedNew || first.id in current.new)
                } else scanEdge != null && first.stamp > scanEdge
                if (!keep) break
                current = page(cursor)
                retained.add(current)
                loadedNew += current.new.size
            }

            val updated = retained.asReversed().flatMap { it.messages }
            if (initial) before = current.before
            rows = when {
                initial -> updated
                reloadRetained -> updated.filter { retainedEdge == null || it.stamp >= retainedEdge }
                else -> (previous + updated).associateBy { it.id }.values.sortedBy { it.stamp }
            }
            val accepted = rows.mapTo(mutableSetOf()) { it.id }
            newIds = ((newIds - updated.map { it.id }.toSet()) + retained.flatMap { it.new }).intersect(accepted)
            rows.forEach { learnedAt(it.id) }
            acceptPage(current, retained)
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

    suspend fun rejectAccess(error: SignInRequired) = reads.withLock {
        applyRead { throw error }
    }

    suspend fun earlier(page: suspend (String?) -> ChatPage): String? = reads.withLock {
        val cursor = before ?: return@withLock null
        var nearest: String? = null
        applyRead {
            val older = page(cursor)
            rows = older.messages + rows
            newIds = newIds + older.new
            older.messages.forEach { learnedAt(it.id) }
            before = older.before
            acceptPage(older, listOf(older))
            nearest = older.messages.lastOrNull(::isNew)?.id
            latest.data
        }
        nearest
    }

    private fun acceptPage(latest: ChatPage, pages: List<ChatPage>) {
        owed = latest.owed
        serverTotal = latest.newTotal
        awaitingClearRead = false
        reports.confirmed(pages.flatMap { page ->
            page.messages.filter { it.tracked && it.id !in page.new }.map { it.id }
        })
    }

    private suspend fun applyRead(read: suspend () -> ChatRead?): Boolean {
        val paired = latest.refresh(read)
        if (latest.authorityLost) {
            reports.reset()
        }
        if (latest.authorityLost && received) {
            rows = emptyList()
            owed = emptyList()
            newIds = emptySet()
            serverTotal = 0
            pendingClear = null
            clearProblem = null
            awaitingClearRead = false
            before = null
            received = false
            boundary = null
            placedVisit = -1
            learned.clear()
            marked.clear()
            timings.clear()
            authorizationEpoch++
        }
        return paired
    }

    fun clear(through: ChatStamp) {
        if (pendingClear != null) return
        val count = newAbove + rows.count { it.stamp <= through && isNew(it) }
        pendingClear = Clear(through, count, SystemClock.elapsedRealtime() + 5_000)
    }

    fun undo() {
        if (pendingClear?.sending == false) pendingClear = null
    }

    fun commitClear(refresh: () -> Unit) {
        reports.launch {
            finishClear()
            refresh()
        }
    }

    private suspend fun finishClear() = clearing.withLock {
        val clear = pendingClear ?: return@withLock
        pendingClear = clear.copy(sending = true)
        try {
            reads.withLock {
                if (pendingClear?.through == clear.through) {
                    val revision = notices.revisionBeforeWrite()
                    api.writeShown("/api/shown/clear", JSONObject().put("through", clear.through.id))
                    val ids = rows.filter { it.tracked && it.stamp <= clear.through }.map { it.id }
                    newIds = newIds - ids.toSet()
                    awaitingClearRead = true
                    reports.confirmed(ids)
                    notices.confirmHeld(revision, ids)
                    clearProblem = null
                }
            }
        } catch (_: IOException) {
            clearProblem = "could not save shown messages"
        } finally {
            pendingClear = null
        }
    }

    fun leave(pausing: Boolean) {
        val departure = notices.foreground(false)
        reports.launch {
            try {
                if (pausing) finishClear()
                reports.flush()
            } finally {
                clearing.withLock { notices.releaseHeld(departure) }
            }
        }
    }

    fun record(messages: List<ChatMessage>, detached: Boolean = false) {
        if (attending) messages.filter { canObserve(it, detached) }.forEach { reports.record(it.id) }
    }

    private data class Dwell(var head: Long = 0, var tail: Long = 0, var accessible: Long = 0, var last: Int = 0)

    fun sample(frame: Long, samples: Map<ChatMessage, Int>, detached: Boolean) {
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
        record(done, detached)
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
    fun Observe(history: ChatHistory, line: Float, hasNew: Boolean, excludedId: String? = null, detached: Boolean = false) {
        val view = LocalView.current
        val accessibility = view.context.getSystemService(AccessibilityManager::class.java)
        LaunchedEffect(this, history.attending, hasNew, line, excludedId, detached) {
            if (!history.attending || !hasNew) return@LaunchedEffect
            try {
                while (true) withFrameMillis { now ->
                    val inner = viewport?.screenRect()
                    val candidates = if (inner == null) emptyList() else cards.values.filter {
                        it.first.id != excludedId && history.canObserve(it.first, detached)
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
                    history.sample(now, samples, detached)
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
