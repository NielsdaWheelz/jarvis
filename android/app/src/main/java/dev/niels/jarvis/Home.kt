package dev.niels.jarvis

import android.app.Activity
import android.net.Uri
import android.os.SystemClock
import androidx.activity.compose.BackHandler
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.CubicBezierEasing
import androidx.compose.animation.core.snap
import androidx.compose.animation.core.tween
import androidx.compose.foundation.gestures.scrollBy
import androidx.compose.foundation.interaction.DragInteraction
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.windowInsetsPadding
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
import androidx.compose.runtime.collectAsState
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
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalWindowInfo
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import java.io.IOException
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale
import java.util.UUID
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.json.JSONException
import org.json.JSONObject

@Composable
internal fun JarvisHome(
    entry: Route, onNavigate: (Route) -> Unit, onResolve: (Route) -> Unit,
    todoReads: () -> TodoReads, history: ChatHistory, notices: PhoneNotices, onBack: (() -> Unit)?,
) {
    val context = LocalContext.current
    val activity = context as Activity
    val access = remember { Access.get(context) }
    val api = remember { HomeApi(context) }
    val drafts = remember { Drafts.get(context) }
    val scope = rememberCoroutineScope()
    // Keep the home visit even when it resolves to the same address as a direct link.
    var homeAddress by rememberSaveable { mutableStateOf<String?>(null) }
    val route = if (entry == Route.Home) homeAddress?.let { Routes.parse(Uri.parse(it)) } ?: entry else entry
    val resolve: (Route) -> Unit = { target ->
        if (entry == Route.Home) homeAddress = Routes.url(target).toString() else onResolve(target)
    }
    var chat by rememberSaveable { mutableStateOf(false) }
    var showDrafts by rememberSaveable { mutableStateOf(false) }
    var draftId by rememberSaveable { mutableStateOf<String?>(null) }
    var creating by remember { mutableStateOf(false) }
    var draftFromChat by rememberSaveable { mutableStateOf(false) }
    var scrollAfterSend by rememberSaveable { mutableStateOf<String?>(null) }
    var localError by remember { mutableStateOf<String?>(null) }
    val panes = rememberSaveableStateHolder()
    val closeOverlay = {
        if (showDrafts) showDrafts = false else chat = false
    }
    BackHandler(enabled = draftId == null && (showDrafts || chat), onBack = closeOverlay)
    var refresh by remember { mutableIntStateOf(0) }
    val authRevision by access.revision.collectAsState()
    val reload = refresh to authRevision
    val signIn = { access.signIn(activity) }
    val setupHome = entry == Route.Home && route != Route.Home && !chat && !showDrafts && draftId == null
    val phone = remember { PhoneAlerts.get(context) }
    LaunchedEffect(reload, setupHome) { phone.refresh(setupHome) }
    val lifecycle = (activity as androidx.lifecycle.LifecycleOwner).lifecycle
    var resumed by remember { mutableStateOf(lifecycle.currentState == Lifecycle.State.RESUMED) }
    val focused = LocalWindowInfo.current.isWindowFocused
    val visibleChat = chat && !showDrafts && draftId == null
    DisposableEffect(lifecycle) {
        val listener = LifecycleEventObserver { _, event ->
            when (event) {
                Lifecycle.Event.ON_RESUME -> {
                    resumed = true
                    refresh++
                }
                Lifecycle.Event.ON_PAUSE -> {
                    history.attend(false)
                    history.finishClear()
                    history.flushBeforeLeaving()
                    notices.foreground(false)
                    resumed = false
                }
                else -> Unit
            }
        }
        lifecycle.addObserver(listener)
        onDispose { lifecycle.removeObserver(listener) }
    }
    DisposableEffect(resumed, visibleChat) {
        notices.foreground(resumed && visibleChat)
        onDispose {
            if (resumed && visibleChat) {
                history.flushBeforeLeaving()
                notices.foreground(false)
            }
        }
    }
    LaunchedEffect(resumed, focused) { history.attend(resumed && focused) }
    val reporting = history.reportPending
    LaunchedEffect(reporting) {
        if (reporting) {
            do {
                delay(1_000)
                history.flushObserved()
            } while (history.reportPending)
        }
    }
    val pending = history.pendingClear
    LaunchedEffect(pending) {
        if (pending != null) {
            delay((pending.deadline - SystemClock.elapsedRealtime()).coerceAtLeast(0))
            history.finishClear()
        }
    }
    val readPage: suspend (String?) -> ChatPage = { before ->
        val active = notices.snapshot()
        val path = "/api/messages" + (before?.let { "?before=${Uri.encode(it)}" } ?: "")
        ChatPage(api.read(path) ?: throw IOException("conversation unavailable")).also { notices.sweep(active, it) }
    }
    LaunchedEffect(resumed, reload, history.visit) {
        if (resumed) {
            history.refresh(revisit = true, readPage)
            while (true) {
                delay(3_000)
                history.refresh(revisit = false, readPage)
            }
        }
    }

    val newDraft: (DiscussionRef?) -> Unit = { ref ->
        if (!creating) {
            creating = true
            scope.launch {
                try {
                    draftFromChat = visibleChat
                    draftId = drafts.create(UUID.randomUUID().toString(), ref).id
                    showDrafts = false
                    localError = null
                } catch (_: IOException) {
                    localError = "could not save a draft on this phone"
                } finally {
                    creating = false
                }
            }
        }
    }
    JarvisPaper {
        Column(Modifier.fillMaxSize().windowInsetsPadding(WindowInsets.safeDrawing).imePadding()) {
            val currentDraft = draftId
            if (currentDraft != null) {
                DraftComposer(currentDraft, onReturn = { draftId = null }) { messageId ->
                    draftId = null
                    refresh++
                    if (draftFromChat) scrollAfterSend = messageId else onNavigate(Route.Message(messageId))
                }
            } else {
                FlowRow(Modifier.padding(horizontal = 8.dp), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    val back = if (chat || showDrafts) closeOverlay else onBack
                    back?.let { TextButton(onClick = it) { Text("back") } }
                    val destinations = listOf(
                        "jarvis" to Route.Home,
                        "todos" to Route.Todos,
                        "artifacts" to Route.Artifacts,
                        "files" to Route.Files,
                    )
                    val section = when (route) {
                        is Route.Todo -> Route.Todos
                        is Route.Artifact -> Route.Artifacts
                        is Route.File, is Route.DriveFile -> Route.Files
                        else -> route
                    }
                    for ((label, target) in destinations) {
                        val selectedSection = section == target && !chat && !showDrafts
                        TextButton(
                            onClick = {
                                if (entry != target) onNavigate(target)
                                else {
                                    chat = false
                                    showDrafts = false
                                }
                            },
                            modifier = Modifier.semantics { selected = selectedSection },
                        ) { Text(label, style = if (selectedSection) MaterialTheme.typography.titleMedium else MaterialTheme.typography.labelLarge) }
                    }
                    if (!chat || showDrafts) TextButton(onClick = {
                        showDrafts = false
                        chat = true
                    }, modifier = Modifier.semantics {
                        contentDescription = if (history.newTotal == 0) "open chat" else "open chat, ${history.newTotal} new"
                    }) { Text(if (history.newTotal == 0) "chat" else "chat · ◇ ${history.newTotal}") }
                    if (!showDrafts) TextButton(onClick = { showDrafts = true }) { Text("drafts") }
                    if (!showDrafts) TextButton(onClick = { refresh++ }) { Text("refresh") }
                }
                HorizontalDivider()
                if (setupHome) PhoneSetupAction(phone, signIn)
                localError?.let { BodyStatus(it) }
                val pane = when {
                    showDrafts -> "drafts"
                    chat -> "chat"
                    else -> "current"
                }
                if (pane == "current" && route is Route.Message) {
                    WorkspaceApprovalPanel(api, authRevision)
                }
                panes.SaveableStateProvider(pane) {
                    when {
                        showDrafts -> DraftList(drafts, { draftId = it }, { newDraft(null) })
                        chat -> Conversation(history, readPage, signIn, onNavigate, newDraft, scrollAfterSend) {
                            WorkspaceApprovalPanel(api, authRevision)
                        }
                        else -> when (route) {
                            Route.Home -> Read("home", reload, signIn, api::selectedHome) { selected ->
                                LaunchedEffect(selected) { resolve(selected?.route() ?: Route.Todos) }
                                Pane { BodyStatus("opening home") }
                            }
                            Route.Todos, is Route.Todo -> TodoViewer((route as? Route.Todo)?.id, todoReads(), api, reload, signIn, onNavigate, newDraft)
                            is Route.Message -> MessageDetail(route, api, reload, signIn, onNavigate, newDraft, history) {
                                chat = true
                            }
                            is Route.Source -> SourcePane(route, api, refresh, authRevision, onNavigate, onBack)
                            is Route.Table -> TablePane(route, api, reload, signIn, onNavigate, onBack)
                            Route.Files -> DriveList(null, api, reload, signIn, onNavigate, newDraft)
                            is Route.File -> OriginPane(route, api, reload, signIn, onResolve)
                            is Route.DriveFile -> FilePane(route, api, reload, signIn, onNavigate, newDraft)
                            is Route.Mail -> Pane {
                                TextButton(onClick = { onNavigate(route) }) { Text("open in browser") }
                                TextButton(onClick = { onNavigate(Route.Message(route.messageId)) }) { Text("open message") }
                            }
                            Route.Artifacts -> ArtifactShelf(api, reload, signIn, onNavigate)
                            is Route.Artifact -> ArtifactPane(route, api, reload, signIn, activity, resolve, onNavigate, newDraft)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun DraftList(drafts: Drafts, open: (String) -> Unit, newDraft: () -> Unit) {
    val revision by drafts.revision.collectAsState()
    var items by remember { mutableStateOf<List<Draft>>(emptyList()) }
    var error by remember { mutableStateOf(false) }
    LaunchedEffect(revision) {
        try {
            items = drafts.list()
            error = false
        } catch (_: IOException) {
            error = true
        }
    }
    LazyColumn(contentPadding = PaddingValues(20.dp)) {
        item { Heading("saved drafts") }
        item { TextButton(onClick = newDraft) { Text("new message") } }
        if (error) item { BodyStatus("could not read drafts saved on this phone") }
        if (items.isEmpty() && !error) item { Text("no drafts saved on this phone") }
        items(items, key = { it.id }) { draft ->
            TextButton(onClick = { open(draft.id) }, modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.fillMaxWidth()) {
                    Text(draft.text.lineSequence().firstOrNull { it.isNotBlank() }?.take(120)
                        ?: draft.files.firstOrNull()?.name ?: draft.ref?.label ?: "untitled draft")
                    Text(when (draft.state) {
                        DraftState.Editing -> "saved on this phone"
                        DraftState.Frozen -> "send unconfirmed"
                        DraftState.Conflict -> "submission conflict"
                        DraftState.Received -> "received"
                    }, style = MaterialTheme.typography.labelMedium)
                }
            }
        }
    }
}

@Composable
private fun Conversation(
    history: ChatHistory, readPage: suspend (String?) -> ChatPage, signIn: () -> Unit,
    navigate: (Route) -> Unit, discuss: (DiscussionRef?) -> Unit, sent: String?,
    approvals: @Composable () -> Unit,
) {
    val list = rememberLazyListState()
    val viewport = remember { ChatViewport() }
    val scope = rememberCoroutineScope()
    val messages = history.rows
    val byId = remember(messages) { messages.associateBy { it.id } }
    val deliveries = remember(messages) { messages.associate { it.id to it.json.deliveries() } }
    val editions = remember(deliveries) { deliveries.values.flatten().filterIsInstance<DiscussionRef.Artifact>() }
    val boundary = history.boundary
    val through = messages.lastOrNull { it.tracked }?.stamp
    val keys = buildList {
        if (history.before != null) add("earlier")
        for (message in messages) {
            if (message.id == boundary) add("boundary")
            add(message.id)
        }
    }
    val indexes = remember(keys) { keys.withIndex().associate { (i, key) -> key to i } }
    var anchor by rememberSaveable { mutableStateOf<String?>(null) }
    var offset by rememberSaveable { mutableIntStateOf(0) }
    var pinned by rememberSaveable { mutableStateOf(true) }
    var appliedVisit by rememberSaveable { mutableIntStateOf(-1) }
    var appliedSend by rememberSaveable { mutableStateOf<String?>(null) }
    var previousHead by rememberSaveable { mutableStateOf<String?>(null) }
    var held by rememberSaveable { mutableStateOf<String?>(null) }
    var restored by remember { mutableStateOf(false) }
    var moving by remember { mutableStateOf(false) }
    var owedCycle by rememberSaveable { mutableStateOf<String?>(null) }
    var pendingJump by remember { mutableStateOf<String?>(null) }
    var announcement by remember { mutableStateOf("") }
    var announcedAt by remember { mutableStateOf<Long?>(null) }
    val line = with(LocalDensity.current) { MaterialTheme.typography.bodyLarge.lineHeight.toPx() }
    val inset = (line * 4.5f).toInt()

    suspend fun bottom() {
        list.scrollToItem(keys.lastIndex)
        list.layoutInfo.visibleItemsInfo.find { it.index == keys.lastIndex }?.let { list.scrollBy(it.size.toFloat()) }
    }

    LaunchedEffect(keys, history.placedVisit, sent) {
        if (keys.isEmpty()) return@LaunchedEffect
        val oldHead = previousHead?.let { id -> messages.indexOfFirst { it.id == id } } ?: -1
        val arrivals = messages.drop(oldHead + 1).filter { it.tracked }
        val oldAnchor = indexes[anchor]
        if (pinned && oldHead >= 0 && held == null) held = arrivals.firstOrNull(history::arrivedAway)?.id
        moving = true
        try {
            when {
                sent != null && appliedSend != sent && sent in byId -> {
                    bottom()
                    pinned = true
                    held = null
                    appliedSend = sent
                }
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
    LaunchedEffect(list) {
        var userScroll = false
        snapshotFlow {
            val item = list.layoutInfo.visibleItemsInfo.firstOrNull { it.index == list.firstVisibleItemIndex }
            Triple(item?.key as? String, list.firstVisibleItemScrollOffset, list.isScrollInProgress && !moving)
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

    viewport.Observe(history, line, history.newTotal > history.newAbove)
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
        val position = indexes[target]
        if (position != null) {
            pinned = false
            moving = true
            try { list.scrollToItem(position, -inset) } finally { moving = false }
            pendingJump = null
        } else {
            val cursor = history.before
            history.earlier(readPage)
            if (history.before == cursor) pendingJump = null
        }
    }
    val jump: (String) -> Unit = { id ->
        val position = indexes[id]
        if (position == null) navigate(Route.Message(id))
        else scope.launch {
            pinned = false
            moving = true
            try { list.scrollToItem(position, -inset) } finally { moving = false }
        }
    }

    Column(Modifier.fillMaxSize()) {
        val problem = history.problem
        if (problem != null) {
            Column(Modifier.padding(horizontal = 20.dp)) {
                BodyStatus(if (problem == "sign in") "sign in to continue" else problem)
                if (problem == "sign in") TextButton(onClick = signIn) { Text("sign in") }
            }
        } else if (!history.received) CircularProgressIndicator(Modifier.padding(20.dp))
        LazyColumn(
            state = list,
            modifier = Modifier.weight(1f).onGloballyPositioned { viewport.viewport = it },
            contentPadding = PaddingValues(horizontal = 24.dp, vertical = 12.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            items(keys, key = { it }) { id ->
                when (id) {
                    "earlier" -> TextButton(onClick = { scope.launch { history.earlier(readPage) } }) { Text("earlier messages") }
                    "boundary" -> {
                        val preceding = messages.getOrNull(messages.indexOfFirst { it.id == boundary } - 1)
                        val label = preceding?.let { "new since ${formattedTime(it.stamp.at.toString())}" } ?: "new messages"
                        val color = if (history.newTotal > 0) MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.onSurfaceVariant
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            HorizontalDivider(Modifier.weight(1f), color = color)
                            Text(label, Modifier.padding(start = 8.dp).semantics { heading() }, style = MaterialTheme.typography.labelMedium, color = color)
                            TextButton(
                                enabled = through != null && history.pendingClear == null && history.newTotal > 0,
                                onClick = { if (through != null) history.clear(through) },
                            ) { Text("clear") }
                        }
                    }
                    else -> byId[id]?.let { message ->
                        ChatCard(
                            message, history, viewport,
                            hiddenTop = {
                                val layout = list.layoutInfo
                                val item = layout.visibleItemsInfo.firstOrNull { it.key == id }
                                if (item == null) 0f else (layout.viewportStartOffset - item.offset).toFloat()
                            },
                            navigate = navigate, discuss = discuss, deliveries = deliveries.getValue(id), editions = editions,
                        )
                        TextButton(onClick = { navigate(Route.Message(id)) }) { Text("open exact message") }
                        HorizontalDivider()
                    }
                }
            }
        }
        if (history.received && messages.isEmpty()) Text("no messages here", Modifier.padding(20.dp))
        val pending = history.pendingClear
        if (pending != null || newAbove + newBelow > 0 || history.owed.isNotEmpty()) {
            HorizontalDivider()
            FlowRow(Modifier.padding(horizontal = 12.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                if (pending != null) {
                    TextButton(onClick = history::undo) { Text("${pending.count} cleared · undo") }
                } else if (newAbove + newBelow > 0) {
                    val text = when {
                        newAbove == 0 -> "$newBelow new below"
                        newBelow == 0 -> "$newAbove new above"
                        else -> "${newAbove + newBelow} new, above and below"
                    }
                    TextButton(onClick = {
                        val target = below.firstOrNull()?.id ?: above.lastOrNull()?.id
                        if (target != null) jump(target)
                        else pendingJump = history.nearestOlder?.id
                    }) { Text("◇ $text") }
                }
                if (history.owed.isNotEmpty()) {
                    val count = history.owed.size
                    val candidates = history.owed.filter { it !in onScreen }
                    TextButton(enabled = candidates.isNotEmpty(), onClick = {
                        val candidate = candidates[(candidates.indexOf(owedCycle) + 1) % candidates.size]
                        owedCycle = candidate
                        jump(candidate)
                    }) { Text(if (count == 1) "1 needs a reply" else "$count need a reply", color = rubric()) }
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
        TextButton(onClick = { discuss(null) }, modifier = Modifier.padding(start = 12.dp)) { Text("new message") }
    }
}

@Composable
private fun MessageDetail(
    route: Route.Message, api: HomeApi, reload: Pair<Int, Int>, signIn: () -> Unit,
    navigate: (Route) -> Unit, discuss: (DiscussionRef?) -> Unit, history: ChatHistory,
    conversation: () -> Unit,
) {
    val path = "/api/messages/${route.id}"
    Read(path, reload, signIn, { api.read(path) }, signInLabel = "sign in to open this reply") { message ->
        if (message == null) {
            Pane { BodyStatus("this message is no longer available") }
            return@Read
        }
        val row = remember(message) { ChatMessage(message) }
        val viewport = remember { ChatViewport() }
        val scroll = rememberScrollState()
        val headingInset = with(LocalDensity.current) { 64.dp.roundToPx() }
        viewport.Observe(history, with(LocalDensity.current) { MaterialTheme.typography.bodyLarge.lineHeight.toPx() }, history.isNew(row))
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
private fun rubric() = if (isSystemInDarkTheme()) Color(0xFFEE9A83) else Color(0xFFA33B25)

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
    val ink = MaterialTheme.colorScheme.onSurface
    val muted = MaterialTheme.colorScheme.onSurfaceVariant
    val selection = MaterialTheme.colorScheme.primary
    val carried = row.id in history.marked
    val dry = if (fresh) snap() else tween<Color>(700, easing = CubicBezierEasing(0.22f, 0.61f, 0.36f, 1f))
    val fill by animateColorAsState(if (fresh || !carried) ink else Color.Transparent, dry, label = "lozenge fill")
    val stroke by animateColorAsState(if (fresh || !carried) ink else muted, dry, label = "lozenge border")
    val direct = { history.record(listOf(row)) }
    Column(Modifier.fillMaxWidth().onGloballyPositioned { viewport.cards[row.id] = row to it }.semantics {
        if (selected) this.selected = true
    }.drawBehind {
        if (selected) drawLine(selection, Offset(-4.dp.toPx(), 0f), Offset(-4.dp.toPx(), size.height), 1.5.dp.toPx())
        if (carried) {
            val radius = 5.dp.toPx()
            val x = -(if (selected) 16.dp else 13.dp).toPx()
            val y = maxOf(7.dp.toPx(), hiddenTop() + 16.dp.toPx())
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
    val links = objects("artifact_links").mapNotNull { DiscussionRef.parse(it) as? DiscussionRef.Artifact }
    val presented = DiscussionRef.parse(optJSONObject("present")?.optJSONObject("ref"))
    return (links + listOfNotNull(presented)).distinct()
}

@Composable
private fun MessageEntry(
    message: JSONObject, navigate: (Route) -> Unit, discuss: (DiscussionRef?) -> Unit,
    deliveries: List<DiscussionRef> = message.deliveries(),
    editions: List<DiscussionRef.Artifact> = deliveries.filterIsInstance<DiscussionRef.Artifact>(),
    owed: Boolean, fresh: Boolean, onExternal: () -> Unit,
) {
    val id = message.getString("id")
    val speaker = if (message.getString("role") == "owner") "you" else "jarvis"
    val stamp = "$speaker · ${formattedTime(message.string("at"))}"
    Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(stamp, Modifier.clearAndSetSemantics {
            contentDescription = if (fresh) "new · $stamp" else stamp
        }, style = MaterialTheme.typography.labelMedium)
        if (owed) Text("needs a reply", color = rubric(), fontSize = 12.sp)
    }
    MessageMarkdown(message, navigate, onExternal)
    for (file in message.objects("files")) {
        val status = if (file.optBoolean("unavailable")) "file unavailable" else originStatus(file)
        TextButton(onClick = { navigate(Route.File(file.getString("id"), null)) }) {
            Text("${file.string("name") ?: "original file"} · $status")
        }
    }
    DiscussionRef.parse(message.optJSONObject("ref"))?.let { ref ->
        TextButton(onClick = { navigate(ref.route()) }) { Text("discussed · ${ref.label}") }
    }
    for (proposal in message.objects("proposals")) {
        HorizontalDivider()
        Section(proposal.getString("title"))
        val revision = proposal.string("draft_revision_id")
        Text(proposal.getString("detail"))
        BodyStatus(proposal.string("status_label") ?: proposal.getString("status").replace('_', ' '))
        if (revision != null) {
            TextButton(onClick = { navigate(Route.Mail(id, revision, historical = true)) }) {
                Text("open draft revision")
            }
        }
        proposal.string("owner_message_id")?.let { owner ->
            TextButton(onClick = { navigate(Route.Message(owner)) }) { Text("owner reply · ${proposal.getString("decision")}") }
        }
        TextButton(onClick = { discuss(DiscussionRef.Proposal(id, proposal.getString("action_id"))) }) {
            Text("reply to ${proposal.getString("title")}")
        }
    }
    val drafts = message.objects("drafts")
    message.string("draft_revision_id")?.takeUnless { revision ->
        drafts.any { it.opt("editable") != true && it.string("create_action_id") == revision }
    }?.let { revision ->
        TextButton(onClick = { navigate(Route.Mail(id, revision, historical = true)) }) { Text("open draft revision") }
    }
    if (message.string("draft_revision_error") == "integrity") {
        BodyStatus("exact revision failed integrity checks")
    }
    drafts.forEachIndexed { index, created ->
        val action = created.getString("create_action_id")
        val subject = created.string("subject").orEmpty().ifBlank { "(no subject)" }
        val repeated = drafts.count { it.string("subject") == created.string("subject") } > 1
        val ordinal = drafts.take(index + 1).count { it.string("subject") == created.string("subject") }
        val name = if (repeated) "$subject · $ordinal" else subject
        val historical = created.opt("editable") != true
        val label = if (historical) "open draft revision" else "open draft"
        TextButton(onClick = { navigate(Route.Mail(id, action, historical)) }) { Text("$label · $name") }
    }
    for (ref in deliveries) {
        val label = if (ref is DiscussionRef.Artifact) ref.labelAmong(editions) else ref.label
        TextButton(onClick = { navigate(ref.route()) }) { Text("open $label") }
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
    private var attempt by mutableIntStateOf(0)

    @Composable
    fun load(key: Any, reload: Pair<Int, Int>, read: suspend () -> T?) {
        LaunchedEffect(this, key, reload, attempt) {
            try {
                data = read()
                checked = Instant.now()
                error = null
            } catch (_: SignInRequired) {
                data = null
                checked = null
                error = "sign in"
            } catch (update: ViewerUpdateRequired) {
                data = null
                checked = null
                error = update.message
            } catch (_: IOException) {
                error = "could not refresh"
            } catch (_: JSONException) {
                error = "could not read this response"
            }
        }
    }

    @Composable
    fun status(signIn: () -> Unit, signInLabel: String = "sign in to continue") {
        val problem = error
        if (problem != null) {
            val message = if (problem == "sign in") signInLabel else problem
            Column(Modifier.padding(horizontal = 20.dp)) {
                BodyStatus(message + (checked?.let { " · last checked ${formattedTime(it.toString())}" } ?: ""))
                if (problem == "sign in") TextButton(onClick = signIn) { Text("sign in") }
                else if (problem != UpdateViewerMessage) TextButton(onClick = { attempt++ }) { Text("retry") }
            }
        } else if (!received) CircularProgressIndicator(Modifier.padding(20.dp))
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
