package dev.niels.jarvis

import android.app.Activity
import android.net.Uri
import android.os.SystemClock
import androidx.activity.compose.BackHandler
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.CubicBezierEasing
import androidx.compose.animation.core.snap
import androidx.compose.animation.core.tween
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.scrollBy
import androidx.compose.foundation.interaction.DragInteraction
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.SizeTransform
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.saveable.rememberSaveableStateHolder
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalWindowInfo
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import java.io.IOException
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.json.JSONException
import org.json.JSONObject

@Composable
internal fun JarvisHome(
    entry: Route, onNavigate: (Route) -> Unit, onResolve: (Route) -> Unit,
    todoReads: () -> TodoReads, history: ChatHistory, notices: PhoneNotices, onBack: (() -> Unit)?,
    api: HomeApi, authRevision: Int, presence: Presence, drafts: Drafts,
    readPage: suspend (String?) -> ChatPage,
    confirmReceipt: suspend () -> Boolean,
    openDock: Boolean, dockOpened: () -> Unit,
) {
    val context = LocalContext.current
    val activity = context as Activity
    val access = remember { Access.get(context) }
    // Keep the home visit even when it resolves to the same address as a direct link.
    var homeAddress by rememberSaveable { mutableStateOf<String?>(null) }
    val route = if (entry == Route.Home) homeAddress?.let { Routes.parse(Uri.parse(it)) } ?: entry else entry
    val resolve: (Route) -> Unit = { target ->
        if (entry == Route.Home) homeAddress = Routes.url(target).toString() else onResolve(target)
    }
    var chat by rememberSaveable { mutableStateOf(false) }
    var focusDock by remember { mutableStateOf(false) }
    var requestedReference by remember { mutableStateOf<DiscussionRef?>(null) }
    var localError by remember { mutableStateOf<String?>(null) }
    val panes = rememberSaveableStateHolder()
    val closeChat = {
        requestedReference = null
        focusDock = false
        chat = false
    }
    BackHandler(enabled = chat, onBack = closeChat)
    LaunchedEffect(openDock) {
        if (openDock) {
            chat = true
            focusDock = true
            dockOpened()
        }
    }
    var refresh by remember { mutableIntStateOf(0) }
    val reload = refresh to authRevision
    var revealPresence by remember(presence.mark) { mutableStateOf(false) }
    val refreshPresence = { presence.requestChat(reload = true) }
    val signIn = { access.signIn(activity) }
    val setupHome = entry == Route.Home && route != Route.Home && !chat
    val phone = remember { PhoneAlerts.get(context) }
    LaunchedEffect(reload, setupHome) { phone.refresh(setupHome) }
    val lifecycle = (activity as androidx.lifecycle.LifecycleOwner).lifecycle
    var resumed by remember { mutableStateOf(lifecycle.currentState == Lifecycle.State.RESUMED) }
    val focused = LocalWindowInfo.current.isWindowFocused
    val haptic = LocalHapticFeedback.current
    val entryHandoff = remember(presence) { presence.handoff }
    LaunchedEffect(presence, chat) { if (chat) presence.requestChat() }
    LaunchedEffect(presence.handoff) {
        if (presence.handoff != null && presence.handoff != entryHandoff && resumed && chat) {
            haptic.performHapticFeedback(HapticFeedbackType.TextHandleMove)
        }
    }
    DisposableEffect(lifecycle) {
        val listener = LifecycleEventObserver { _, event ->
            when (event) {
                Lifecycle.Event.ON_RESUME -> {
                    resumed = true
                    refresh++
                }
                Lifecycle.Event.ON_PAUSE -> {
                    history.attend(false)
                    history.leave(pausing = true)
                    resumed = false
                }
                else -> Unit
            }
        }
        lifecycle.addObserver(listener)
        onDispose { lifecycle.removeObserver(listener) }
    }
    DisposableEffect(resumed, chat) {
        if (resumed && chat) notices.foreground(true)
        onDispose {
            if (resumed && chat && lifecycle.currentState == Lifecycle.State.RESUMED) {
                history.leave(pausing = false)
            }
        }
    }
    LaunchedEffect(resumed, focused) { history.attend(resumed && focused) }
    LaunchedEffect(resumed, authRevision) {
        if (resumed) notices.retireUnsupportedChecks(api)
    }
    LaunchedEffect(presence, history.visit) { if (history.visit > 0) presence.requestChat() }
    val pending = history.pendingClear
    LaunchedEffect(pending?.through) {
        if (pending != null) {
            delay((pending.deadline - SystemClock.elapsedRealtime()).coerceAtLeast(0))
            history.commitClear { presence.requestChat() }
        }
    }

    val discuss: (DiscussionRef?) -> Unit = { ref ->
        if (drafts.locked) {
            localError = SettleEarlier
        } else {
            val current = drafts.draft?.ref
            if (ref != null && current != null && current != ref) requestedReference = ref
            else if (ref != null) drafts.reference(ref)
            chat = true
            focusDock = true
            localError = null
        }
    }
    JarvisPaper {
        Column(Modifier.fillMaxSize().windowInsetsPadding(WindowInsets.safeDrawing).imePadding()) {
            FlowRow(Modifier.padding(horizontal = 8.dp), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                PresenceWordmark(
                    presence, route == Route.Home && !chat,
                    openHome = {
                        if (entry != Route.Home) onNavigate(Route.Home) else closeChat()
                    },
                    activate = {
                        when (presence.mark) {
                            PresenceMark.OWED -> {
                                val owed = presence.nextOwed(if (chat) Route.Home else route)
                                if (owed != null) onNavigate(owed) else chat = true
                            }
                            PresenceMark.OWNER -> revealPresence = !revealPresence
                            else -> refreshPresence()
                        }
                    },
                    reveal = { revealPresence = it },
                )
                val back = if (chat) closeChat else onBack
                back?.let { TextButton(onClick = it) { Text("back") } }
                val destinations = listOf("todos" to Route.Todos, "artifacts" to Route.Artifacts, "files" to Route.Files)
                val section = when (route) {
                    is Route.Todo -> Route.Todos
                    is Route.Artifact -> Route.Artifacts
                    is Route.File, is Route.DriveFile -> Route.Files
                    else -> route
                }
                for ((label, target) in destinations) {
                    val selectedSection = section == target && !chat
                    TextButton(
                        onClick = { if (entry != target) onNavigate(target) else closeChat() },
                        modifier = Modifier.semantics { selected = selectedSection },
                    ) { Text(label, style = if (selectedSection) MaterialTheme.typography.titleMedium else MaterialTheme.typography.labelLarge) }
                }
                if (!chat) TextButton(onClick = { chat = true }, modifier = Modifier.semantics {
                    contentDescription = if (history.newTotal == 0) "open chat" else "open chat, ${history.newTotal} new"
                }) { Text(if (history.newTotal == 0) "chat" else "chat · ◇ ${history.newTotal}") }
                TextButton(onClick = {
                    refresh++
                    refreshPresence()
                }) { Text("refresh") }
            }
            PresenceDivider(presence, revealPresence)
            if (setupHome) PhoneSetupAction(phone, signIn)
            localError?.let { BodyStatus(it) }
            if (!chat && route is Route.Message) WorkspaceApprovalPanel(api, authRevision)
            panes.SaveableStateProvider(if (chat) "chat" else "current") {
                if (chat) Conversation(history, readPage, signIn, onNavigate, discuss, presence, refreshPresence,
                    dock = { pressed ->
                        ChatDock(drafts, focusDock, { focusDock = false }, requestedReference, { requestedReference = null }) { words ->
                            if (drafts.send(words, api, history)) pressed()
                        }
                    }) {
                    WorkspaceApprovalPanel(api, authRevision)
                } else when (route) {
                    Route.Home -> Read("home", reload, signIn, api::selectedHome) { selected ->
                        LaunchedEffect(selected) { resolve(selected?.route() ?: Route.Todos) }
                        Pane { BodyStatus("opening home") }
                    }
                    Route.Todos, is Route.Todo -> TodoViewer((route as? Route.Todo)?.id, todoReads(), api, reload, signIn, onNavigate, discuss)
                    is Route.Message -> MessageDetail(route, api, reload, signIn, onNavigate, discuss, history,
                        drafts.sending, confirmReceipt) { chat = true }
                    is Route.Source -> SourcePane(route, api, refresh, authRevision, onNavigate, onBack)
                    is Route.Table -> TablePane(route, api, reload, signIn, onNavigate, onBack)
                    Route.Files -> DriveList(null, api, reload, signIn, onNavigate, discuss)
                    is Route.File -> OriginPane(route, api, reload, signIn, onResolve)
                    is Route.DriveFile -> FilePane(route, api, reload, signIn, onNavigate, discuss)
                    is Route.Mail -> Pane {
                        TextButton(onClick = { onNavigate(route) }) { Text("open in browser") }
                        TextButton(onClick = { onNavigate(Route.Message(route.messageId)) }) { Text("open message") }
                    }
                    Route.Artifacts -> ArtifactShelf(api, reload, signIn, onNavigate)
                    is Route.Artifact -> ArtifactPane(route, api, reload, signIn, activity, resolve, onNavigate, discuss)
                }
            }
        }
    }
}

private sealed interface ConversationEnd {
    data class Waiting(val tail: PresenceTail) : ConversationEnd
    data class Reply(val message: ChatMessage) : ConversationEnd
}

@Composable
private fun Conversation(
    history: ChatHistory, readPage: suspend (String?) -> ChatPage, signIn: () -> Unit,
    navigate: (Route) -> Unit, discuss: (DiscussionRef?) -> Unit, presence: Presence,
    refresh: () -> Unit, dock: @Composable (() -> Unit) -> Unit, approvals: @Composable () -> Unit,
) {
    val list = rememberLazyListState()
    val viewport = remember { ChatViewport() }
    val scope = rememberCoroutineScope()
    val messages = history.rows
    val byId = remember(messages) { messages.associateBy { it.id } }
    val deliveries = remember(messages) { messages.associate { it.id to it.json.deliveries() } }
    val editions = remember(deliveries) { deliveries.values.flatten().filterIsInstance<DiscussionRef.Artifact>() }
    val boundary = history.boundary
    val tail = presence.tail
    // A backdated reply keeps its chronological row while the provisional tail fades.
    val final = messages.lastOrNull()?.takeIf { tail == null && it.id == presence.handoff }
    val end = tail?.let(ConversationEnd::Waiting) ?: final?.let(ConversationEnd::Reply)
    val transition = rememberPresenceTransition(end, "reply handoff")
    val showTail = final == null && (tail != null || transition.currentState is ConversationEnd.Waiting)
    val reduced = !android.animation.ValueAnimator.areAnimatorsEnabled()
    val loaded = history.latest.received || messages.isNotEmpty()
    val through = messages.lastOrNull { it.tracked }?.stamp
    val zone = ZoneId.systemDefault()
    val heads = mutableMapOf<String, LocalDate>()
    val keys = buildList {
        if (history.before != null) add("earlier")
        var previousDay: LocalDate? = null
        for (message in messages) {
            if (message.id == boundary) add("boundary")
            val day = message.stamp.at.atZone(zone).toLocalDate()
            if (day != previousDay) {
                val head = "day-$day"
                heads[head] = day
                add(head)
                previousDay = day
            }
            add(message.id)
        }
        if (showTail) add("tail")
    }
    val indexes = remember(keys) { keys.withIndex().associate { (i, key) -> key to i } }
    var anchor by rememberSaveable { mutableStateOf<String?>(null) }
    var offset by rememberSaveable { mutableIntStateOf(0) }
    var pinned by rememberSaveable { mutableStateOf(true) }
    var appliedVisit by rememberSaveable { mutableIntStateOf(-1) }
    var previousHead by rememberSaveable { mutableStateOf<String?>(null) }
    var held by rememberSaveable { mutableStateOf<String?>(null) }
    var restored by remember(history.authorizationEpoch) { mutableStateOf(false) }
    var restoreSearchFailed by remember(history.authorizationEpoch) { mutableStateOf(false) }
    var moving by remember { mutableStateOf(false) }
    var press by remember { mutableIntStateOf(0) }
    var appliedPress by remember { mutableIntStateOf(0) }
    var appliedCrossing by rememberSaveable { mutableIntStateOf(history.crossing) }
    var height by remember { mutableIntStateOf(0) }
    var placedHeight by remember { mutableIntStateOf(0) }
    var owedCycle by rememberSaveable { mutableStateOf<String?>(null) }
    var pendingJump by remember { mutableStateOf<String?>(null) }
    var announcement by remember { mutableStateOf("") }
    var announcedAt by remember { mutableStateOf<Long?>(null) }
    val line = with(LocalDensity.current) { ChatBodySize.toPx() * 1.5f }
    val inset = (line * 4.5f).toInt()

    suspend fun bottom() {
        list.scrollToItem(keys.lastIndex)
        list.layoutInfo.visibleItemsInfo.find { it.index == keys.lastIndex }?.let { list.scrollBy(it.size.toFloat()) }
    }

    val fetchingAnchor = !restored && !restoreSearchFailed &&
        anchor?.let { it !in indexes } == true && history.before != null
    LaunchedEffect(keys, history.placedVisit, history.crossing, press, height, fetchingAnchor, loaded, tail?.words, history.authorizationEpoch) {
        if (!loaded) {
            restored = false
            return@LaunchedEffect
        }
        if (keys.isEmpty()) return@LaunchedEffect
        if (fetchingAnchor) {
            val cursor = history.before
            history.earlier(readPage)
            restoreSearchFailed = history.before == cursor
            return@LaunchedEffect
        }
        val oldHead = previousHead?.let { id -> messages.indexOfFirst { it.id == id } } ?: -1
        val arrivals = messages.drop(oldHead + 1).filter { it.tracked }
        val oldAnchor = indexes[anchor]
        if (pinned && oldHead >= 0 && held == null) held = arrivals.firstOrNull(history::arrivedAway)?.id
        moving = true
        try {
            when {
                pinned && (press != appliedPress || history.crossing != appliedCrossing) -> bottom()
                !restored && oldAnchor != null -> list.scrollToItem(oldAnchor, offset)
                !restored || (pinned && appliedVisit != history.placedVisit) -> {
                    val oldest = messages.firstOrNull()?.id
                    val target = when {
                        history.newAbove > 0 -> if (boundary != null && boundary == oldest) "boundary" else oldest
                        boundary != null -> "boundary"
                        else -> messages.firstOrNull(history::isNew)?.id
                    }
                    val index = indexes[target]
                    if (index == null) bottom() else list.scrollToItem(index, -inset)
                    held = null
                }
                pinned && height != placedHeight -> bottom()
                pinned && history.attending && oldHead >= 0 && arrivals.isNotEmpty() -> {
                    val layout = list.layoutInfo
                    val first = layout.visibleItemsInfo.firstNotNullOfOrNull { item ->
                        byId[item.key]?.takeIf(history::isNew)
                    } ?: byId[held]?.takeIf(history::isNew) ?: arrivals.firstOrNull(history::isNew)
                    val index = indexes[first?.id]
                    val visible = layout.visibleItemsInfo.find { it.index == index }
                    if (visible != null) {
                        list.scrollBy((visible.offset - layout.viewportStartOffset - inset).coerceAtLeast(0).toFloat())
                    } else if (index != null && first?.id != held && index > (layout.visibleItemsInfo.lastOrNull()?.index ?: -1)) {
                        list.scrollToItem(index, -inset)
                    }
                }
                pinned && history.attending && showTail && held == null &&
                    arrivals.isEmpty() && messages.none(history::isNew) -> bottom()
            }
            if (oldHead >= 0 && arrivals.isNotEmpty()) {
                val now = SystemClock.elapsedRealtime()
                if (announcedAt?.let { now - it >= 10_000 } != false) {
                    val owe = arrivals.count { it.id in history.owed }
                    val suffix = when (owe) {
                        0 -> ""
                        1 -> ", one needs a reply"
                        else -> ", $owe need a reply"
                    }
                    announcement = "${arrivals.size} new from jarvis$suffix"
                    announcedAt = now
                }
            }
            restored = true
            previousHead = messages.lastOrNull()?.id
            appliedVisit = history.placedVisit
            appliedPress = press
            appliedCrossing = history.crossing
            placedHeight = height
        } finally {
            moving = false
        }
    }

    LaunchedEffect(list) {
        list.interactionSource.interactions.collect {
            if (it is DragInteraction.Start) {
                pinned = false
                held = null
                pendingJump = null
            }
        }
    }
    LaunchedEffect(list, history.authorizationEpoch) {
        var userScroll = false
        snapshotFlow {
            val item = list.layoutInfo.visibleItemsInfo.firstOrNull {
                it.index >= list.firstVisibleItemIndex && (it.key as? String)?.let(::canonicalUuid) == true
            }
            Triple(item?.key as? String, item?.let { -it.offset } ?: 0, list.isScrollInProgress && !moving)
        }.collect { (id, pixels, scrolling) ->
            if (restored && id != null) {
                anchor = id
                offset = pixels
                if (scrolling) {
                    userScroll = true
                    pinned = false
                    held = null
                } else if (userScroll) {
                    userScroll = false
                    pinned = !list.canScrollForward
                }
            }
        }
    }

    val entering = final?.id?.takeIf { transition.currentState is ConversationEnd.Waiting }
    viewport.Observe(history, line, loaded && restored && history.newTotal > history.newAbove, entering)
    val visible = list.layoutInfo.visibleItemsInfo
    val onScreen = visible.mapTo(mutableSetOf()) { it.key }
    val firstIndex = visible.firstOrNull()?.index ?: 0
    val lastIndex = visible.lastOrNull()?.index ?: -1
    val above = messages.filter { history.isNew(it) && indexes.getValue(it.id) < firstIndex }
    val below = messages.filter { history.isNew(it) && indexes.getValue(it.id) > lastIndex }
    val newAbove = above.size + history.newAbove
    val newBelow = below.size
    LaunchedEffect(pendingJump, keys) {
        val target = pendingJump ?: return@LaunchedEffect
        val position = indexes[target] ?: return@LaunchedEffect
        pinned = false
        moving = true
        try { list.scrollToItem(position, -inset) } finally { moving = false }
        pendingJump = null
    }
    var seekingOlder by remember { mutableStateOf(false) }
    val jump: (String) -> Unit = { id ->
        val position = indexes[id]
        if (position == null) navigate(Route.Message(id))
        else scope.launch {
            pinned = false
            moving = true
            try { list.scrollToItem(position, -inset) } finally { moving = false }
        }
    }

    val top: (String) -> Int = { id ->
        val previous = keys.getOrNull(indexes.getValue(id) - 1)
        when {
            previous == null -> 0
            previous in heads || previous == "boundary" -> 6
            byId[id]?.owner == true -> 30
            byId[previous]?.owner == true -> 6
            else -> 24
        }
    }
    val density = LocalDensity.current
    val showMessage: @Composable (ChatMessage) -> Unit = { message ->
        ChatCard(
            message, history, viewport,
            hiddenTop = {
                val layout = list.layoutInfo
                val item = layout.visibleItemsInfo.firstOrNull { it.key == message.id }
                if (item == null) 0f else (layout.viewportStartOffset - item.offset) - with(density) { top(message.id).dp.toPx() }
            },
            navigate = navigate, discuss = discuss, deliveries = deliveries.getValue(message.id), editions = editions,
        )
    }
    val showEnd: @Composable () -> Unit = {
        transition.AnimatedContent(
            transitionSpec = {
                (fadeIn(tween(if (reduced) 120 else 280)) togetherWith
                    fadeOut(tween(if (reduced) 120 else if (targetState == null) 200 else 160)))
                    .using(SizeTransform(clip = false) { _, _ -> snap() })
            },
            contentKey = { if (it is ConversationEnd.Reply) it.message.id else it?.javaClass },
        ) { content ->
            when (content) {
                is ConversationEnd.Waiting -> ProvisionalReply(content.tail, presence.beat)
                is ConversationEnd.Reply -> if (content.message.id == final?.id) {
                    Column { showMessage(content.message) }
                }
                null -> Unit
            }
        }
    }

    Column(Modifier.fillMaxSize()) {
        history.latest.status(signIn, retry = refresh, opening = "opening conversation")
        history.writeProblem?.let { BodyStatus(it) }
        if (!loaded || fetchingAnchor) {
            Box(Modifier.weight(1f)) {
                if (fetchingAnchor) Text("opening conversation", Modifier.padding(24.dp), style = ChatMurmur)
            }
        } else LazyColumn(
            state = list,
            modifier = Modifier.weight(1f).onGloballyPositioned { viewport.viewport = it }
                .onSizeChanged { height = it.height },
            contentPadding = PaddingValues(start = 24.dp, end = 16.dp, bottom = 12.dp),
        ) {
            items(keys, key = { it }) { id ->
                when (id) {
                    "earlier" -> ChatWord("earlier messages", { scope.launch { history.earlier(readPage) } })
                    "boundary" -> {
                        val preceding = messages.getOrNull(messages.indexOfFirst { it.id == boundary } - 1)
                        val label = preceding?.let { "new since ${shortTime(it.stamp.at)}" } ?: "new messages"
                        val color = if (history.newTotal > 0) MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.onSurfaceVariant
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            HorizontalDivider(Modifier.weight(1f), color = color)
                            Text(label, Modifier.padding(start = 8.dp).semantics { heading() }, style = ChatMurmur, color = color)
                            ChatWord("clear", { if (through != null) history.clear(through) },
                                enabled = through != null && history.pendingClear == null && history.newTotal > 0)
                        }
                    }
                    "tail", final?.id -> Box(Modifier.padding(top = top(id).dp)) { showEnd() }
                    else -> {
                        val day = heads[id]
                        if (day != null) {
                            val words = day.format(DateTimeFormatter.ofPattern("EEEE d MMMM", Locale.ENGLISH)).lowercase(Locale.ROOT)
                            val title = if (day.year == LocalDate.now(zone).year) words else "$words ${day.year}"
                            Text(title, Modifier.padding(top = if (indexes.getValue(id) == 0) 0.dp else 48.dp)
                                .semantics { heading() }, style = ChatMurmur.copy(
                                    fontStyle = FontStyle.Normal, fontSize = 22.sp,
                                ))
                        } else byId[id]?.let { message ->
                            Box(Modifier.padding(top = top(id).dp)) { showMessage(message) }
                        }
                    }
                }
            }
        }
        if (loaded && messages.isEmpty() && !showTail) Text("no messages here", Modifier.padding(20.dp), style = ChatMurmur)
        val pending = history.pendingClear?.takeUnless { it.sending }
        if (pending != null || newAbove + newBelow > 0 || history.owed.isNotEmpty()) {
            HorizontalDivider()
            FlowRow(Modifier.padding(horizontal = 12.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                if (pending != null) {
                    TextButton(onClick = history::undo) { Text("${pending.count} cleared · undo", style = ChatMurmur) }
                } else if (newAbove + newBelow > 0) {
                    val text = when {
                        newAbove == 0 -> "$newBelow new below"
                        newBelow == 0 -> "$newAbove new above"
                        else -> "${newAbove + newBelow} new, above and below"
                    }
                    TextButton(enabled = !seekingOlder, onClick = {
                        val target = below.firstOrNull()?.id ?: above.lastOrNull()?.id
                        if (target != null) jump(target)
                        else scope.launch {
                            seekingOlder = true
                            try {
                                while (history.before != null && pendingJump == null) {
                                    val cursor = history.before
                                    pendingJump = history.earlier(readPage)
                                    if (history.before == cursor) break
                                }
                            } finally {
                                seekingOlder = false
                            }
                        }
                    }) { Text("◇ $text", style = ChatMurmur) }
                }
                if (history.owed.isNotEmpty()) {
                    val count = history.owed.size
                    val candidates = history.owed.filter { it !in onScreen }
                    TextButton(enabled = candidates.isNotEmpty(), onClick = {
                        val candidate = candidates[(candidates.indexOf(owedCycle) + 1) % candidates.size]
                        owedCycle = candidate
                        jump(candidate)
                    }) { Text(if (count == 1) "1 needs a reply" else "$count need a reply", color = rubric(), style = ChatCaps) }
                }
            }
        }
        if (announcement.isNotEmpty()) {
            Box(Modifier.semantics {
                liveRegion = LiveRegionMode.Polite
                contentDescription = announcement
            })
        }
        approvals()
        dock {
            pinned = true
            held = null
            pendingJump = null
            press++
        }
    }
}

@Composable
private fun MessageDetail(
    route: Route.Message, api: HomeApi, reload: Pair<Int, Int>, signIn: () -> Unit,
    navigate: (Route) -> Unit, discuss: (DiscussionRef?) -> Unit, history: ChatHistory,
    sending: Boolean, confirmReceipt: suspend () -> Boolean,
    conversation: () -> Unit,
) {
    val scroll = rememberScrollState()
    if (history.latest.authorityLost) {
        history.latest.status(signIn, signInLabel = "sign in to open this reply")
        return
    }
    val path = "/api/messages/${route.id}"
    Read(path to sending, reload, signIn, {
        val epoch = history.authorizationEpoch
        try {
            val row = api.read(path)?.also {
                if (it.optString("id") != route.id) throw IOException("invalid message response")
            }
            if (!confirmReceipt() || epoch != history.authorizationEpoch) throw ChatPageDeferred()
            row
        } catch (lost: SignInRequired) {
            history.rejectAccess(lost)
            throw lost
        } catch (stale: ViewerUpdateRequired) {
            history.rejectAccess(stale)
            throw stale
        }
    }, signInLabel = "sign in to open this reply") { message ->
        if (message == null) {
            Pane { BodyStatus("this message is no longer available") }
            return@Read
        }
        val row = remember(message) { ChatMessage(message) }
        val viewport = remember { ChatViewport() }
        val headingInset = with(LocalDensity.current) { 64.dp.roundToPx() }
        viewport.Observe(history, with(LocalDensity.current) { ChatBodySize.toPx() * 1.5f },
            history.canObserve(row, detached = true), detached = true)
        Column(
            Modifier.fillMaxSize().onGloballyPositioned { viewport.viewport = it }.verticalScroll(scroll).padding(24.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Heading("message")
            ChatCard(row, history, viewport, selected = true,
                hiddenTop = { (scroll.value - headingInset).coerceAtLeast(0).toFloat() },
                navigate = navigate, discuss = discuss,
            )
            TextButton(onClick = conversation) { Text("all conversation") }
        }
    }
}

@Composable
private fun ChatCard(
    row: ChatMessage, history: ChatHistory, viewport: ChatViewport, selected: Boolean = false,
    hiddenTop: () -> Float, navigate: (Route) -> Unit, discuss: (DiscussionRef?) -> Unit,
    deliveries: List<DiscussionRef> = row.json.deliveries(),
    editions: List<DiscussionRef.Artifact> = deliveries.filterIsInstance<DiscussionRef.Artifact>(),
) {
    val fresh = history.isNew(row)
    LaunchedEffect(row.id, history.visit, fresh) {
        if (fresh) {
            delay((history.learnedAt(row.id) + 1_500 - SystemClock.elapsedRealtime()).coerceAtLeast(0))
            if (history.isNew(row)) history.marked[row.id] = Unit
        }
    }
    DisposableEffect(row.id, viewport) { onDispose { viewport.cards.remove(row.id) } }
    val firstLine = with(LocalDensity.current) { 12.sp.toPx() * 1.4f + ChatBodySize.toPx() * .75f + 2.dp.toPx() }
    val ink = MaterialTheme.colorScheme.onSurface
    val muted = MaterialTheme.colorScheme.onSurfaceVariant
    val selection = MaterialTheme.colorScheme.primary
    val carried = row.id in history.marked
    val dry = if (fresh) snap() else tween<Color>(700, easing = CubicBezierEasing(0.22f, 0.61f, 0.36f, 1f))
    val fill by animateColorAsState(if (fresh || !carried) ink else Color.Transparent, dry, label = "lozenge fill")
    val stroke by animateColorAsState(if (fresh || !carried) ink else muted, dry, label = "lozenge border")
    val direct = { history.record(listOf(row), detached = selected) }
    Column(Modifier.fillMaxWidth().onGloballyPositioned { viewport.cards[row.id] = row to it }.semantics {
        if (selected) this.selected = true
    }.drawBehind {
        if (selected) drawLine(selection, Offset(-23.dp.toPx(), 0f),
            Offset(-23.dp.toPx(), size.height), 2.dp.toPx())
        if (row.owner) drawLine(muted, Offset(-18.dp.toPx(), firstLine), Offset(-9.dp.toPx(), firstLine), 1.5.dp.toPx())
        if (!row.owner && carried) {
            val radius = 5.dp.toPx()
            val x = -13.dp.toPx()
            val y = maxOf(firstLine, hiddenTop() + 16.dp.toPx())
                .coerceAtMost((size.height - radius).coerceAtLeast(radius))
            val diamond = Path().apply {
                moveTo(x, y - radius)
                lineTo(x + radius, y)
                lineTo(x, y + radius)
                lineTo(x - radius, y)
                close()
            }
            drawPath(diamond, fill)
            drawPath(diamond, stroke, style = Stroke(1.5.dp.toPx()))
        }
    }) {
        MessageEntry(
            row.json, { direct(); navigate(it) }, { direct(); discuss(it) }, deliveries, editions,
            owed = row.id in history.owed, fresh = fresh && carried, onExternal = direct,
        )
    }
}

private fun JSONObject.deliveries(): List<DiscussionRef> {
    val links = objects("artifact_links").mapNotNull(DiscussionRef::parse)
    val presented = DiscussionRef.parse(optJSONObject("present")?.optJSONObject("ref"))
    return (links + listOfNotNull(presented)).distinct()
}

private data class ApparatusEntry(val kind: String, val text: String, val route: Route? = null, val note: String? = null)

private fun JSONObject.apparatus(deliveries: List<DiscussionRef>, editions: List<DiscussionRef.Artifact>): List<ApparatusEntry> = buildList {
    val id = getString("id")
    val reference = DiscussionRef.parse(optJSONObject("ref"))
    if (reference != null) add(ApparatusEntry("about", reference.label, reference.route()))
    val files = objects("files")
    for (file in files) {
        val note = when {
            file.optBoolean("unavailable") -> "file unavailable"
            file.string("state") == "filed" -> "filed"
            else -> originStatus(file)
        }
        add(ApparatusEntry("file", file.string("name") ?: "unnamed file", Route.File(file.getString("id"), null), note))
    }
    val drafts = objects("drafts")
    fun subject(row: JSONObject) = row.string("subject").orEmpty().ifBlank { "(no subject)" }
    val repeated = drafts.filter { it.optBoolean("editable") }.groupingBy(::subject).eachCount()
    val ordinals = mutableMapOf<String, Int>()
    for (draft in drafts.sortedBy { !it.optBoolean("editable") }) {
        val editable = draft.optBoolean("editable")
        val subject = subject(draft)
        val ordinal = if (editable && repeated.getValue(subject) > 1) {
            ((ordinals[subject] ?: 0) + 1).also { ordinals[subject] = it }
        } else null
        add(ApparatusEntry(if (editable) "draft" else "revision", ordinal?.let { "$subject · $it" } ?: subject,
            Route.Mail(id, draft.getString("create_action_id"), historical = !editable)))
    }
    val revision = string("draft_revision_id")
    val badRevision = string("draft_revision_error") == "integrity"
    if (revision != null && drafts.none { it.opt("editable") != true && it.string("create_action_id") == revision }) {
        add(ApparatusEntry("revision", "draft revision", Route.Mail(id, revision, historical = true),
            "failed integrity checks".takeIf { badRevision }))
    } else if (badRevision) add(ApparatusEntry("revision", "draft revision", note = "failed integrity checks"))
    for (ref in deliveries) {
        if (ref == reference || (ref is DiscussionRef.File && ref.page == null && files.any { it.string("id") == ref.id })) continue
        add(when (ref) {
            is DiscussionRef.Artifact -> ApparatusEntry("artifact", ref.labelAmong(editions), ref.route())
            is DiscussionRef.File -> ApparatusEntry("file", "original file", ref.route(), ref.page?.let { "page $it" })
            is DiscussionRef.DriveFile -> ApparatusEntry("file", "drive file", ref.route(), ref.page?.let { "page $it" })
            is DiscussionRef.Todo -> ApparatusEntry("todo", ref.label, ref.route())
            is DiscussionRef.Proposal -> continue
        })
    }
}

@Composable
private fun Apparatus(rows: List<ApparatusEntry>, navigate: (Route) -> Unit) {
    if (rows.isEmpty()) return
    val colors = MaterialTheme.colorScheme
    val measure = rememberTextMeasurer()
    val width = with(LocalDensity.current) {
        rows.maxOf { measure.measure(it.kind, ChatCaps, softWrap = false).size.width }.toDp()
    }
    var previous: String? = null
    for (entry in rows) {
        val first = entry.kind != previous
        previous = entry.kind
        val name = listOfNotNull(entry.kind, entry.text, entry.note).joinToString(" · ")
        val row = Modifier.fillMaxWidth().heightIn(min = 48.dp)
        Row(if (entry.route == null) row else row.clickable(role = Role.Button) { navigate(entry.route) }
            .semantics { contentDescription = name }, horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically) {
            Text(if (first) entry.kind else "", Modifier.width(width), color = colors.onSurfaceVariant, style = ChatCaps,
                softWrap = false)
            Column(Modifier.weight(1f).then(if (entry.route == null) Modifier else Modifier.clearAndSetSemantics {})) {
                Text(entry.text, style = ChatApparatus.copy(
                    textDecoration = if (entry.route != null) TextDecoration.Underline else null,
                ))
                entry.note?.let { Text(it, style = ChatMurmur, color = colors.onSurfaceVariant) }
            }
        }
    }
}

@Composable
private fun MessageEntry(
    message: JSONObject, navigate: (Route) -> Unit, discuss: (DiscussionRef?) -> Unit,
    deliveries: List<DiscussionRef>, editions: List<DiscussionRef.Artifact>,
    owed: Boolean, fresh: Boolean, onExternal: () -> Unit,
) {
    val id = message.getString("id")
    MessageStamp(if (message.getString("role") == "owner") "you" else "jarvis", shortTime(Instant.parse(message.getString("at"))),
        owed, fresh)
    Spacer(Modifier.height(2.dp))
    MessageMarkdown(message, navigate, onExternal)
    val rows = remember(message, deliveries, editions) { message.apparatus(deliveries, editions) }
    Apparatus(rows, navigate)
    message.optJSONObject("workspace_block")?.let { WorkspaceBlockEntry(it) }
    for (proposal in message.objects("proposals")) {
        val status = proposal.getString("status")
        Box(Modifier.fillMaxWidth().padding(top = 10.dp, start = 18.dp)) {
            if (owed && status == "awaiting_approval") {
                Text("¶", Modifier.offset(x = (-18).dp).clearAndSetSemantics {}, color = rubric(), style = ChatMurmur)
            }
            Column {
                Text(proposal.getString("title"), style = chatBody())
                Text(proposal.getString("detail"), style = ChatApparatus)
                Apparatus(buildList {
                    proposal.string("draft_revision_id")?.let {
                        add(ApparatusEntry("revision", "draft revision", Route.Mail(id, it, historical = true)))
                    }
                    proposal.string("owner_message_id")?.let {
                        add(ApparatusEntry("you", if (proposal.string("decision") == "approve") "approved" else "denied", Route.Message(it)))
                    }
                }, navigate)
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically) {
                    Text(proposal.string("status_label") ?: status.replace('_', ' '),
                        Modifier.weight(1f).padding(start = 12.dp), style = ChatCaps.copy(textAlign = androidx.compose.ui.text.style.TextAlign.End),
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
    }
}

@Composable
internal fun Pane(content: @Composable ColumnScope.() -> Unit) {
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
        content = content,
    )
}

@Composable
internal fun Section(title: String) {
    Text(title, Modifier.semantics { heading() }, style = MaterialTheme.typography.titleMedium)
}

internal class ReadState<T> {
    var data by mutableStateOf<T?>(null)
        private set
    private var checked by mutableStateOf<Instant?>(null)
    val received get() = checked != null
    private var error by mutableStateOf<String?>(null)
    val settled get() = received || error != null
    val signedOut get() = error == "sign in"
    val authorityLost get() = signedOut || error == UpdateViewerMessage
    private var attempt by mutableIntStateOf(0)

    suspend fun refresh(read: suspend () -> T?): Boolean {
        error = try {
            data = read()
            checked = Instant.now()
            null
        } catch (_: ChatPageDeferred) {
            return false
        } catch (update: ViewerUpdateRequired) {
            data = null
            checked = null
            update.message
        } catch (_: SignInRequired) {
            data = null
            checked = null
            "sign in"
        } catch (_: IOException) {
            "could not refresh"
        } catch (_: JSONException) {
            "could not read this response"
        }
        return error == null
    }

    @Composable
    fun load(key: Any, reload: Pair<Int, Int>, read: suspend () -> T?) {
        LaunchedEffect(this, key, reload, attempt) { refresh(read) }
    }

    @Composable
    fun status(signIn: () -> Unit, signInLabel: String = "sign in to continue", retry: (() -> Unit)? = null, opening: String? = null) {
        val problem = error
        if (problem != null) {
            val message = if (problem == "sign in") signInLabel else problem
            Column(Modifier.padding(horizontal = 20.dp)) {
                BodyStatus(message + (checked?.let { " · last checked ${formattedTime(it.toString())}" } ?: ""))
                if (problem == "sign in") TextButton(onClick = signIn) { Text("sign in") }
                else if (problem != UpdateViewerMessage) TextButton(onClick = { if (retry != null) retry() else attempt++ }) { Text("retry") }
            }
        } else if (!received) {
            if (opening == null) CircularProgressIndicator(Modifier.padding(20.dp))
            else Text(opening, Modifier.padding(20.dp), style = ChatMurmur)
        }
    }
}

@Composable
internal fun <T> Read(
    key: Any,
    reload: Pair<Int, Int>,
    signIn: () -> Unit,
    load: suspend () -> T?,
    signInLabel: String = "sign in to continue",
    content: @Composable (T?) -> Unit,
) {
    val state = remember(key) { ReadState<T>() }
    state.load(key, reload, load)
    state.status(signIn, signInLabel)
    if (state.received) content(state.data)
}

internal fun formattedTime(value: String?, timezone: String? = null): String {
    if (value == null) return ""
    val zone = timezone?.let(ZoneId::of) ?: ZoneId.systemDefault()
    return DateTimeFormatter.ofPattern("MMM d, h:mm a${if (timezone != null) " z" else ""}", Locale.getDefault())
        .withZone(zone).format(Instant.parse(value))
}

internal fun civilDate(value: String): String =
    LocalDate.parse(value).format(DateTimeFormatter.ofPattern("MMM d", Locale.getDefault()))
