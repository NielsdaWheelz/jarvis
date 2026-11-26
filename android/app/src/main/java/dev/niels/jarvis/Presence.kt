package dev.niels.jarvis

import android.animation.ValueAnimator
import android.os.SystemClock.elapsedRealtime
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.Crossfade
import androidx.compose.animation.ExperimentalAnimationApi
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.CubicBezierEasing
import androidx.compose.animation.core.SeekableTransitionState
import androidx.compose.animation.core.Transition
import androidx.compose.animation.core.rememberTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.wrapContentHeight
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.MotionDurationScale
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.repeatOnLifecycle
import java.io.IOException
import java.time.DateTimeException
import java.time.Duration
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import org.json.JSONException
import org.json.JSONObject

private const val tickMillis = 3000L
private const val readMillis = 2500L

private enum class Phase { IDLE, QUEUED, WORKING, STANDBY, RETRYING, PAUSED }
internal enum class PresenceMark { NONE, RECEIVED, OWNER, QUIET, OWED, REST }

private data class WorkSample(
    val since: Instant, val triggers: List<String>, val family: String?, val writing: Boolean,
) {
    val forOwner get() = "you" in triggers
    val words get() = when (family) {
        null -> "thinking"
        "gmail" -> if (writing) "writing mail" else "reading mail"
        "calendar" -> if (writing) "updating the calendar" else "checking the calendar"
        "drive", "docs" -> if (writing) "writing to drive" else "reading drive"
        "maps" -> "checking maps"
        "memory" -> if (writing) "taking a note" else "searching memory"
        "web" -> "reading the web"
        "work" -> if (writing) "updating todos" else "checking todos"
        "agent" -> "working with a worker"
        "receipt" -> "rereading a source"
        "shell" -> "running a command"
        else -> "working"
    }
    val triggerWords get() = when (triggers.firstOrNull()) {
        "mail" -> "from mail"
        "todo" -> "from your todos"
        "result" -> "a result came back"
        "recovery" -> "recovering"
        else -> null
    }
}

private data class OwnerWork(val phase: Phase, val ahead: Int)

private data class Sample(
    val at: Instant, val phase: Phase, val until: Instant?, val reason: String?,
    val draining: Boolean, val work: WorkSample?, val owner: OwnerWork?,
    val workers: Int, val owed: List<Route.Message?>, val chat: String,
) {
    val statusWords get() = when (phase) {
        Phase.PAUSED -> if (draining) "pausing" else "paused"
        Phase.STANDBY -> if (reason == "quota") {
            "out of quota" + (until?.let { " · reset reported ${shortTime(it)}" } ?: "")
        } else "can't reach the model" + (until?.let { " · next try ${shortTime(it)}" } ?: "")
        Phase.RETRYING -> "next try ${shortTime(checkNotNull(until))}"
        else -> ""
    }

    val tailWords get() = when (owner?.phase) {
        Phase.WORKING -> work?.takeIf { it.forOwner }?.words ?: "working"
        Phase.QUEUED -> if (owner.ahead > 0 || work != null) "received · after current work" else "received"
        Phase.STANDBY, Phase.RETRYING, Phase.PAUSED -> statusWords
        else -> null
    }

    companion object {
        fun decode(json: JSONObject): Sample = with(json) {
            require(keys().asSequence().toSet() == setOf("as_of", "state", "until", "reason", "draining", "work", "you", "queued", "workers", "owed", "chat"))
            val phase = Phase.valueOf(getString("state").uppercase())
            val until = string("until")?.let(Instant::parse)
            val reason = string("reason")
            require(if (phase == Phase.STANDBY) reason in setOf("quota", "unavailable") else reason == null)
            require(phase != Phase.RETRYING || until != null)
            val work = optJSONObject("work")?.let {
                val triggers = it.getJSONArray("triggers")
                val family = it.string("activity")
                val mode = it.string("mode")
                require(if (family == null) mode == null else mode in setOf("read", "write"))
                WorkSample(Instant.parse(it.getString("since")), List(triggers.length()) { i -> triggers.getString(i) },
                    family, mode == "write")
            }
            val draining = getBoolean("draining")
            require(phase == Phase.PAUSED || work == null || phase == Phase.WORKING)
            require(phase != Phase.WORKING || work != null)
            require(draining == (phase == Phase.PAUSED && work != null))
            val owner = optJSONObject("you")?.let {
                val state = Phase.valueOf(it.getString("state").uppercase())
                val ahead = it.getInt("ahead")
                require(state != Phase.IDLE && ahead >= 0)
                OwnerWork(state, ahead)
            }
            val queued = getJSONObject("queued")
            val workers = getInt("workers")
            require(queued.getInt("you") >= 0 && queued.getInt("other") >= 0 && workers >= 0)
            val owed = getJSONArray("owed").objects().map {
                when (it.getString("kind")) {
                    "google" -> {
                        require(it.isNull("href"))
                        null
                    }
                    "approval", "owner_input" -> {
                        val href = it.getString("href")
                        val id = href.removePrefix("/m/")
                        require(href == "/m/$id" && canonicalUuid(id))
                        Route.Message(id)
                    }
                    else -> throw IllegalArgumentException("invalid owed kind")
                }
            }
            Sample(Instant.parse(getString("as_of")), phase, until, reason, draining, work, owner,
                workers, owed, getString("chat"))
        }
    }
}

internal data class PresenceTail(
    val words: String,
    val shape: PresenceMark,
    val started: Long? = null,
    val frozen: Long? = null,
    val lastHeard: String? = null,
) {
    val mark get() = if (frozen == null && lastHeard == null) shape else PresenceMark.NONE
}

internal class Presence {
    var tail by mutableStateOf<PresenceTail?>(null)
        private set
    var handoff by mutableStateOf<String?>(null)
        private set
    var beat by mutableLongStateOf(0L)
        private set
    var stale by mutableStateOf(false)
        private set
    var announcement by mutableStateOf("")
        private set
    private var sample by mutableStateOf<Sample?>(null)
    private var lastHeard: Instant? = null
    private var ownerHeard: Instant? = null
    private var knownStart: Long? = null
    private var etag: String? = null
    private var unsupported = false
    private var failures = 0
    private var pairedFailures = 0
    private var refreshAll = false
    private var receiptEpoch = 0L
    private val wake = Channel<Unit>(Channel.CONFLATED)
    private val unpaired = mutableSetOf<String>()

    val hasReading get() = sample != null && !stale
    val mark get() = when {
        stale -> PresenceMark.NONE
        sample?.phase == Phase.PAUSED -> PresenceMark.REST
        sample?.owed?.isNotEmpty() == true -> PresenceMark.OWED
        sample?.work?.forOwner == true -> PresenceMark.OWNER
        sample?.phase in setOf(Phase.STANDBY, Phase.RETRYING) -> PresenceMark.REST
        sample?.work != null || (sample?.workers ?: 0) > 0 -> PresenceMark.QUIET
        sample?.owner?.phase == Phase.QUEUED -> PresenceMark.RECEIVED
        else -> PresenceMark.NONE
    }
    val legend get() = when (mark) {
        PresenceMark.NONE -> if (stale) lastHeardWords(lastHeard) else ""
        PresenceMark.REST -> sample?.statusWords.orEmpty()
        PresenceMark.OWNER -> sample?.work?.words.orEmpty()
        PresenceMark.QUIET -> sample?.work?.let { work ->
            listOfNotNull(work.triggerWords, work.words).joinToString(" · ")
        } ?: sample?.workers?.let { if (it == 1) "1 worker running" else "$it workers running" }.orEmpty()
        PresenceMark.OWED -> "waiting on you"
        PresenceMark.RECEIVED -> ""
    }
    val description get() = when (mark) {
        PresenceMark.NONE -> legend
        PresenceMark.OWNER -> "jarvis is $legend for you"
        PresenceMark.RECEIVED -> "jarvis has received your message"
        PresenceMark.OWED -> "jarvis is waiting on you"
        PresenceMark.REST -> when (sample?.phase) {
            Phase.PAUSED -> "jarvis is $legend"
            Phase.STANDBY -> if (sample?.reason == "quota") "jarvis is $legend" else "jarvis $legend"
            else -> "jarvis will try again at ${sample?.until?.let(::shortTime).orEmpty()}"
        }
        PresenceMark.QUIET -> sample?.work?.let {
            "jarvis is ${it.words}" + (it.triggerWords?.let { trigger -> " · $trigger" } ?: "")
        } ?: if (sample?.workers == 1) "1 worker is running" else "${sample?.workers} workers are running"
    }

    fun nextOwed(current: Route): Route.Message? {
        val owed = sample?.owed.orEmpty()
        val next = owed.indexOfFirst { it == current } + 1
        return owed.getOrNull(if (next < owed.size) next else 0)
    }

    private fun announce(words: String) {
        announcement = if (announcement == words) "${words}\u200b" else words
    }

    fun accepted() {
        receiptEpoch++
        handoff = null
        if (hasReading) tail = PresenceTail("received", PresenceMark.RECEIVED)
        announce("received.")
        requestChat()
    }

    fun requestChat(reload: Boolean = false) {
        if (reload) {
            unsupported = false
            refreshAll = true
        }
        wake.trySend(Unit)
    }

    private fun markStale() {
        stale = true
        tail = tail?.let { it.copy(frozen = it.frozen ?: elapsedRealtime(), lastHeard = lastHeardWords(lastHeard)) }
    }

    private suspend fun confirm(api: HomeApi, history: ChatHistory): Sample? {
        if (unsupported) return null
        val headers = etag?.let { mapOf("If-None-Match" to it) }.orEmpty()
        val (code, payload, tag) = try {
            withContext(Dispatchers.IO) {
                api.request("/api/presence", headers = headers, retryAuthentication = false, timeoutMillis = readMillis)
                    .use { response ->
                        val decoded = if (response.code == 200) Sample.decode(response.json()) else null
                        Triple(response.code, decoded, response.header("ETag"))
                    }
            }
        } catch (signedOut: SignInRequired) {
            history.rejectAccess(signedOut)
            markStale()
            return null
        } catch (_: IOException) {
            null
        } catch (_: JSONException) {
            null
        } catch (_: DateTimeException) {
            null
        } catch (_: IllegalArgumentException) {
            null
        } ?: Triple(0, null, null)
        val checked = when (code) {
            304 -> sample
            200 -> payload?.takeIf { tag != null && tag.startsWith('"') && tag.endsWith('"') }?.also { etag = tag }
            404 -> {
                unsupported = true
                etag = null
                sample = null
                knownStart = null
                tail = null
                stale = false
                announcement = ""
                failures = 0
                pairedFailures = 0
                unpaired.clear()
                return null
            }
            else -> null
        }
        if (checked == null) {
            if (++failures >= 3) markStale()
            return null
        }
        if (checked.work?.since != sample?.work?.since) {
            knownStart = checked.work?.let { elapsedRealtime() - Duration.between(it.since, checked.at).toMillis().coerceAtLeast(0) }
        }
        if (sample?.phase != checked.phase) {
            when (checked.phase) {
                Phase.STANDBY -> announce(checked.statusWords.substringBefore(" · "))
                Phase.RETRYING -> announce("retrying")
                Phase.PAUSED -> announce("paused")
                else -> Unit
            }
        }
        failures = 0
        stale = false
        lastHeard = Instant.now()
        sample = checked
        beat++
        return checked
    }

    suspend fun poll(api: HomeApi, history: ChatHistory, notices: PhoneNotices) {
        unsupported = false
        var readVisit: Int? = null
        var pairedToken: String? = null
        while (true) {
            val began = elapsedRealtime()
            val sampledEpoch = receiptEpoch
            val checked = confirm(api, history)
            val settling = checked != null && checked.owner == null && tail != null && sampledEpoch == receiptEpoch
            if (settling) tail = tail?.let { it.copy(frozen = it.frozen ?: elapsedRealtime()) }
            if (checked?.owner != null && sampledEpoch == receiptEpoch) {
                handoff = null
                val hasOwnerWork = checked.work?.forOwner == true
                val shape = when (checked.owner.phase) {
                    Phase.QUEUED -> PresenceMark.RECEIVED
                    Phase.WORKING -> if (hasOwnerWork) PresenceMark.OWNER else PresenceMark.REST
                    else -> PresenceMark.REST
                }
                val start = knownStart.takeIf { hasOwnerWork && checked.owner.phase in setOf(Phase.WORKING, Phase.PAUSED) }
                tail = checked.tailWords?.let { PresenceTail(it, shape, start) }
                ownerHeard = lastHeard
                pairedFailures = 0
            }
            val visit = history.visit
            val revisit = refreshAll || readVisit != visit || (checked != null && checked.chat != pairedToken)
            refreshAll = false
            val paired = history.refresh(revisit) { before -> readChatPage(api, notices, before, readMillis) }
            var arrivals = emptySet<String>()
            if (paired) {
                readVisit = visit
                if (checked != null) pairedToken = checked.chat
                val read = checkNotNull(history.latest.data)
                arrivals = read.arrivals
                unpaired += arrivals
                if (checked != null && sampledEpoch == receiptEpoch) {
                    pairedFailures = 0
                    if (checked.owner == null) {
                        if (tail != null) handoff = read.finals.lastOrNull { it in unpaired }
                        tail = null
                        unpaired.clear()
                    } else if (arrivals.isEmpty()) {
                        unpaired.clear()
                    }
                }
            } else {
                if (revisit) refreshAll = true
                if (history.latest.signedOut) markStale()
                else if (settling && sampledEpoch == receiptEpoch && ++pairedFailures >= 3) tail = tail?.copy(lastHeard = lastHeardWords(ownerHeard))
            }
            if (arrivals.isEmpty() || unsupported) {
                withTimeoutOrNull((tickMillis - elapsedRealtime() + began).coerceAtLeast(0)) { wake.receive() }
            }
        }
    }
}

private fun shortTime(at: Instant): String =
    DateTimeFormatter.ofPattern("HH:mm").withZone(ZoneId.systemDefault()).format(at)

private fun lastHeardWords(at: Instant?): String = at?.let { "last heard ${shortTime(it)}" } ?: "not connected"

@Composable
internal fun rememberPresence(api: HomeApi, authRevision: Int, history: ChatHistory, notices: PhoneNotices): Presence {
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    val presence = remember(authRevision) { Presence() }
    LaunchedEffect(lifecycle, api, presence, history, notices) {
        lifecycle.repeatOnLifecycle(Lifecycle.State.RESUMED) { presence.poll(api, history, notices) }
    }
    return presence
}

// Presence supplies its own reduced-motion durations, including at system scale zero.
private object PresenceMotionTime : MotionDurationScale {
    override val scaleFactor = 1f
}

@Composable
internal fun <T> rememberPresenceTransition(target: T, label: String): Transition<T> {
    val driver = remember { SeekableTransitionState(target) }
    val transition = rememberTransition(driver, label = label)
    LaunchedEffect(target) {
        withContext(PresenceMotionTime) { driver.animateTo(target) }
    }
    return transition
}

private val cormorant = FontFamily(
    Font(R.font.cormorant_garamond_regular),
    Font(R.font.cormorant_garamond_italic, style = FontStyle.Italic),
)

@Composable
internal fun PresenceWordmark(
    presence: Presence, selected: Boolean, openHome: () -> Unit, activate: () -> Unit,
    reveal: (Boolean) -> Unit,
) {
    val mark = presence.mark
    val wordmarkOpacity by rememberPresenceTransition(presence.stale, "wordmark")
        .animateFloat(transitionSpec = { tween(if (ValueAnimator.areAnimatorsEnabled()) 600 else 120) }, label = "ink") {
            if (it) .65f else 1f
        }
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(
            modifier = Modifier.heightIn(min = 48.dp).widthIn(min = 48.dp).clickable(role = Role.Button, onClick = openHome)
                .padding(start = 12.dp, end = 3.dp).semantics {
                    this.selected = selected
                    if (presence.description.isNotEmpty()) stateDescription = presence.description
                },
            contentAlignment = Alignment.Center,
        ) {
            Text("jarvis", modifier = Modifier.alpha(wordmarkOpacity),
                style = MaterialTheme.typography.titleLarge.copy(fontFamily = cormorant))
        }
        val control = if (mark == PresenceMark.NONE) Modifier else Modifier.onFocusChanged { reveal(it.isFocused) }
            .clickable(role = Role.Button, onClick = activate)
            .semantics { contentDescription = presence.description }
        Box(Modifier.size(48.dp).then(control), contentAlignment = Alignment.CenterStart) {
            if (presence.hasReading) {
                Box(Modifier.offset(x = (-8).dp, y = 3.dp)) { PresencePoint(mark, presence.beat) }
            }
        }
    }
}

@Composable
internal fun PresenceDivider(presence: Presence, revealed: Boolean) {
    val legend = presence.legend.takeUnless { presence.mark == PresenceMark.OWNER && !revealed }.orEmpty()
    Box(Modifier.fillMaxWidth().height(1.dp)) {
        HorizontalDivider()
        if (legend.isNotEmpty()) {
            Text(legend, modifier = Modifier.padding(start = 12.dp, end = 12.dp)
                .wrapContentHeight(Alignment.CenterVertically, unbounded = true)
                .background(MaterialTheme.colorScheme.background).padding(horizontal = 4.dp),
                maxLines = 1, overflow = TextOverflow.Ellipsis, color = MaterialTheme.colorScheme.onSurfaceVariant,
                style = MaterialTheme.typography.labelLarge.copy(fontFamily = cormorant, fontStyle = FontStyle.Italic))
        }
        // Stable live region; the graphics and their changing descriptions stay quiet.
        Text(presence.announcement, modifier = Modifier.size(1.dp).semantics { liveRegion = LiveRegionMode.Polite },
            color = Color.Transparent)
    }
    Spacer(Modifier.height(8.dp))
}

@OptIn(ExperimentalAnimationApi::class)
@Composable
private fun PresencePoint(mark: PresenceMark, beat: Long) {
    val reduced = !ValueAnimator.areAnimatorsEnabled()
    val colors = MaterialTheme.colorScheme
    val rubric = Color(if (isSystemInDarkTheme()) 0xFFEE9A83 else 0xFFA33B25)
    rememberPresenceTransition(mark, "presence shape").Crossfade(animationSpec = tween(if (reduced) 120 else 240)) { shape ->
        if (shape == PresenceMark.OWED) {
            Text("¶", color = rubric, style = MaterialTheme.typography.titleLarge.copy(fontFamily = cormorant))
        } else {
            val scale = remember { Animatable(1f) }
            val echo = remember { Animatable(0f) }
            val opacity = remember { Animatable(1f) }
            val owner = shape == PresenceMark.OWNER
            val quiet = shape == PresenceMark.QUIET
            LaunchedEffect(shape, beat, reduced) {
                if (shape != mark || !(owner || quiet)) return@LaunchedEffect
                withContext(PresenceMotionTime) {
                    scale.snapTo(if (quiet) .86f else 1f)
                    echo.snapTo(0f)
                    opacity.snapTo(1f)
                    if (reduced) {
                        if (owner) {
                            opacity.animateTo(.45f, tween(450))
                            opacity.animateTo(1f, tween(450))
                        }
                    } else coroutineScope {
                        launch {
                            scale.animateTo(if (owner) 1.34f else 1.06f,
                                tween(if (owner) 132 else 224, easing = CubicBezierEasing(.2f, 0f, 0f, 1f)))
                            scale.animateTo(if (owner) 1f else .86f,
                                tween(if (owner) 1068 else 1376, easing = CubicBezierEasing(.3f, 0f, .1f, 1f)))
                        }
                        launch {
                            echo.animateTo(1f, tween(if (owner) 1800 else 2000,
                                easing = CubicBezierEasing(.15f, .6f, .25f, 1f)))
                        }
                    }
                }
            }
            Canvas(Modifier.size(24.dp)) {
                val radius = 3.dp.toPx()
                when (shape) {
                    PresenceMark.OWNER, PresenceMark.QUIET -> {
                        val color = if (owner) colors.primary else colors.onSurfaceVariant
                        val t = echo.value
                        if (!reduced && t > 0f && t < 1f) {
                            drawCircle(color, radius * (1f + t * if (owner) 3.4f else 2f),
                                alpha = (1f - t) * if (owner) .85f else .5f)
                        }
                        drawCircle(color, radius * scale.value, alpha = opacity.value)
                    }
                    PresenceMark.RECEIVED, PresenceMark.REST -> drawCircle(
                        if (shape == PresenceMark.RECEIVED) colors.primary else colors.onSurfaceVariant,
                        radius, style = Stroke(1.dp.toPx()),
                    )
                    else -> Unit
                }
            }
        }
    }
}

@Composable
internal fun ProvisionalReply(tail: PresenceTail, beat: Long) {
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    var now by remember { mutableLongStateOf(elapsedRealtime()) }
    LaunchedEffect(lifecycle, tail.started, tail.frozen) {
        if (tail.started != null && tail.frozen == null) lifecycle.repeatOnLifecycle(Lifecycle.State.RESUMED) {
            while (true) {
                now = elapsedRealtime()
                delay(1000)
            }
        }
    }
    val seconds = tail.started?.let { ((tail.frozen ?: now) - it) / 1000 }
    val reduced = !ValueAnimator.areAnimatorsEnabled()
    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("jarvis", style = MaterialTheme.typography.labelMedium)
            if (seconds != null && seconds >= 20) {
                val digits = "${seconds / 60}:${(seconds % 60).toString().padStart(2, '0')}"
                Text(digits, modifier = Modifier.alpha(if (tail.lastHeard != null) .55f else 1f),
                    style = MaterialTheme.typography.labelMedium.copy(fontFeatureSettings = "tnum"))
            }
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            if (tail.mark == PresenceMark.NONE) Spacer(Modifier.size(24.dp))
            else PresencePoint(tail.mark, beat)
            rememberPresenceTransition(tail.words, "presence words").AnimatedContent(transitionSpec = {
                (fadeIn(tween(if (reduced) 120 else 220, delayMillis = if (reduced) 0 else 140)) togetherWith
                    fadeOut(tween(if (reduced) 120 else 140))).using(null)
            }) {
                Text(it, color = MaterialTheme.colorScheme.onSurfaceVariant,
                    style = MaterialTheme.typography.bodyLarge.copy(fontFamily = cormorant, fontStyle = FontStyle.Italic))
            }
        }
        tail.lastHeard?.let {
            Text(it, color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.labelSmall)
        }
    }
}
