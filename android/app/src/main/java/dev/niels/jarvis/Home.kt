package dev.niels.jarvis

import android.app.Activity
import android.net.Uri
import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.SizeTransform
import androidx.compose.animation.core.snap
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
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
import androidx.compose.runtime.SideEffect
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
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import java.io.IOException
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale
import java.util.UUID
import kotlinx.coroutines.flow.drop
import kotlinx.coroutines.launch
import org.json.JSONException
import org.json.JSONObject

@Composable
internal fun JarvisHome(
    entry: Route, onNavigate: (Route) -> Unit, onResolve: (Route) -> Unit,
    todoReads: () -> TodoReads, onBack: (() -> Unit)?,
    api: HomeApi, authRevision: Int, presence: Presence,
) {
    val context = LocalContext.current
    val activity = context as Activity
    val access = remember { Access.get(context) }
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
    var localError by remember { mutableStateOf<String?>(null) }
    val panes = rememberSaveableStateHolder()
    val closeOverlay = {
        if (showDrafts) showDrafts = false else chat = false
    }
    BackHandler(enabled = draftId == null && (showDrafts || chat), onBack = closeOverlay)
    var refresh by remember { mutableIntStateOf(0) }
    val reload = refresh to authRevision
    var sent by rememberSaveable { mutableStateOf<String?>(null) }
    val chatOpen = chat && !showDrafts && draftId == null
    LaunchedEffect(presence, chatOpen) { if (chatOpen) presence.requestChat() }
    var revealPresence by remember(presence.mark) { mutableStateOf(false) }
    val refreshPresence = { presence.requestChat(reload = true) }
    val signIn = { access.signIn(activity) }
    val setupHome = entry == Route.Home && route != Route.Home && !chat && !showDrafts && draftId == null
    val phone = remember { PhoneAlerts.get(context) }
    LaunchedEffect(reload, setupHome) { phone.refresh(setupHome) }
    DisposableEffect(activity) {
        val lifecycle = (activity as androidx.lifecycle.LifecycleOwner).lifecycle
        val listener = LifecycleEventObserver { _, event -> if (event == Lifecycle.Event.ON_RESUME) refresh++ }
        lifecycle.addObserver(listener)
        onDispose { lifecycle.removeObserver(listener) }
    }

    val newDraft: (DiscussionRef?) -> Unit = { ref ->
        if (!creating) {
            creating = true
            scope.launch {
                try {
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
                    chat = true
                    showDrafts = false
                    sent = messageId
                    presence.accepted()
                }
            } else {
                FlowRow(Modifier.padding(horizontal = 8.dp), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    PresenceWordmark(
                        presence, route == Route.Home && !chat && !showDrafts,
                        openHome = {
                            if (entry != Route.Home) onNavigate(Route.Home) else closeOverlay()
                        },
                        activate = {
                            when (presence.mark) {
                                PresenceMark.OWED -> {
                                    val owed = presence.nextOwed(if (chat) Route.Home else route)
                                    if (owed != null) onNavigate(owed) else {
                                        showDrafts = false
                                        chat = true
                                    }
                                }
                                PresenceMark.OWNER -> revealPresence = !revealPresence
                                else -> refreshPresence()
                            }
                        },
                        reveal = { revealPresence = it },
                    )
                    val back = if (chat || showDrafts) closeOverlay else onBack
                    back?.let { TextButton(onClick = it) { Text("back") } }
                    val destinations = listOf(
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
                    }) { Text("chat") }
                    if (!showDrafts) TextButton(onClick = { showDrafts = true }) { Text("drafts") }
                    if (!showDrafts) TextButton(onClick = {
                        refresh++
                        refreshPresence()
                    }) { Text("refresh") }
                }
                PresenceDivider(presence, revealPresence)
                if (setupHome) PhoneSetupAction(phone, signIn)
                localError?.let { BodyStatus(it) }
                val pane = when {
                    showDrafts -> "drafts"
                    chat -> "chat"
                    else -> "current"
                }
                if (pane == "chat" || (pane == "current" && route is Route.Message)) {
                    WorkspaceApprovalPanel(api, authRevision)
                }
                panes.SaveableStateProvider(pane) {
                    when {
                        showDrafts -> DraftList(drafts, { draftId = it }, { newDraft(null) })
                        chat -> Conversation(api, reload, signIn, onNavigate, newDraft, presence, sent,
                            refreshPresence, { sent = null })
                        else -> when (route) {
                            Route.Home -> Read("home", reload, signIn, api::selectedHome) { selected ->
                                LaunchedEffect(selected) { resolve(selected?.route() ?: Route.Todos) }
                                Pane { BodyStatus("opening home") }
                            }
                            Route.Todos, is Route.Todo -> TodoViewer((route as? Route.Todo)?.id, todoReads(), api, reload, signIn, onNavigate, newDraft)
                            is Route.Message -> MessageDetail(route, api, reload, signIn, onNavigate, newDraft) {
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

private sealed interface ConversationEnd {
    data class Waiting(val tail: PresenceTail) : ConversationEnd
    data class Reply(val message: JSONObject) : ConversationEnd
}

@Composable
private fun Conversation(
    api: HomeApi,
    reload: Pair<Int, Int>,
    signIn: () -> Unit,
    navigate: (Route) -> Unit,
    discuss: (DiscussionRef?) -> Unit,
    presence: Presence,
    sent: String?,
    refresh: () -> Unit,
    onSentVisible: () -> Unit,
) {
    var before by rememberSaveable { mutableStateOf<String?>(null) }
    LaunchedEffect(sent) { if (sent != null) before = null }
    val edge = before
    val read = if (edge == null) presence.latest else {
        val path = "/api/messages?before=${Uri.encode(edge)}"
        remember(edge) { ReadState<JSONObject>() }.apply { load(path, reload) { api.read(path) } }
    }
    read.status(signIn, retry = refresh.takeIf { edge == null })
    if (!read.received) return

    val page = read.data
    val messages = page?.objects("items").orEmpty()
    val tail = presence.tail.takeIf { edge == null }
    // A backdated reply keeps its chronological row and the tail fades in place.
    val final = messages.lastOrNull()?.takeIf { tail == null && edge == null && it.string("id") == presence.handoff }
    val end = tail?.let(ConversationEnd::Waiting) ?: final?.let(ConversationEnd::Reply)
    val transition = rememberPresenceTransition(end, "reply handoff")
    val showEnd = transition.currentState != null || end != null
    val reduced = !android.animation.ValueAnimator.areAnimatorsEnabled()
    val deliveries = messages.associateWith { it.deliveries() }
    val editions = deliveries.values.flatten().filterIsInstance<DiscussionRef.Artifact>()
    val showMessage: @Composable (JSONObject) -> Unit = { message ->
        MessageEntry(message, navigate, discuss, deliveries[message] ?: message.deliveries(), editions)
        TextButton(onClick = { navigate(Route.Message(message.getString("id"))) }) { Text("open exact message") }
        HorizontalDivider()
    }
    val scroll = rememberLazyListState()
    var pinned by rememberSaveable { mutableStateOf(false) }
    LaunchedEffect(scroll) {
        snapshotFlow { scroll.isScrollInProgress }.drop(1).collect { moving ->
            pinned = !moving && !scroll.canScrollForward
        }
    }
    val previous = page?.string("next_before")
    val count = 2 + (if (edge != null) 1 else 0) + (if (previous != null) 1 else 0) +
        messages.size.coerceAtLeast(1) - (if (final != null) 1 else 0) + (if (showEnd) 1 else 0)
    val layout = Triple(page, count, transition.currentState != transition.targetState)
    var positioned by remember { mutableStateOf<Triple<JSONObject?, Int, Boolean>?>(null) }
    SideEffect {
        val sentVisible = edge == null && sent != null && messages.any { it.string("id") == sent }
        if (sentVisible || (edge == null && pinned && positioned != layout)) {
            scroll.requestScrollToItem(count - 1)
            pinned = true
        }
        positioned = layout
        if (sentVisible) onSentVisible()
    }
    LazyColumn(state = scroll, contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item("heading") { Heading("chat") }
        item("write") { TextButton(onClick = { discuss(null) }) { Text("new message") } }
        if (edge != null) item("latest") { TextButton(onClick = { before = null }) { Text("latest messages") } }
        if (previous != null) item("previous") { TextButton(onClick = { before = previous }) { Text("earlier messages") } }
        if (messages.isEmpty()) item("empty") { Text("no messages here") }
        items(if (final == null) messages else messages.dropLast(1), key = { it.getString("id") }) { message ->
            showMessage(message)
        }
        if (showEnd) item("tail") {
            transition.AnimatedContent(
                transitionSpec = {
                    (fadeIn(tween(if (reduced) 120 else 280)) togetherWith
                        fadeOut(tween(if (reduced) 120 else if (targetState == null) 200 else 160)))
                        .using(SizeTransform(clip = false) { _, _ -> snap() })
                },
                contentKey = { if (it is ConversationEnd.Reply) it.message.getString("id") else it?.javaClass },
            ) { content ->
                when (content) {
                    is ConversationEnd.Waiting -> ProvisionalReply(content.tail, presence.beat)
                    is ConversationEnd.Reply -> Column { showMessage(content.message) }
                    null -> Unit
                }
            }
        }
    }
}

@Composable
private fun MessageDetail(
    route: Route.Message,
    api: HomeApi,
    reload: Pair<Int, Int>,
    signIn: () -> Unit,
    navigate: (Route) -> Unit,
    discuss: (DiscussionRef?) -> Unit,
    conversation: () -> Unit,
) {
    val path = "/api/messages/${route.id}"
    Read(path, reload, signIn, { api.read(path) }, signInLabel = "sign in to open this reply") { message ->
        Pane {
            if (message == null) {
                BodyStatus("this message is no longer available")
                return@Pane
            }
            Heading("message")
            MessageEntry(message, navigate, discuss)
            TextButton(onClick = conversation) { Text("all conversation") }
        }
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
) {
    val id = message.getString("id")
    val speaker = if (message.getString("role") == "owner") "you" else "jarvis"
    Text("$speaker · ${formattedTime(message.string("at"))}", style = MaterialTheme.typography.labelMedium)
    MessageMarkdown(message, navigate)
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
    val signedOut get() = error == "sign in"
    private var attempt by mutableIntStateOf(0)

    suspend fun refresh(read: suspend () -> T?): Boolean {
        error = try {
            data = read()
            checked = Instant.now()
            null
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
    fun status(signIn: () -> Unit, signInLabel: String = "sign in to continue", retry: (() -> Unit)? = null) {
        val problem = error
        if (problem != null) {
            val message = if (problem == "sign in") signInLabel else problem
            Column(Modifier.padding(horizontal = 20.dp)) {
                BodyStatus(message + (checked?.let { " · last checked ${formattedTime(it.toString())}" } ?: ""))
                if (problem == "sign in") TextButton(onClick = signIn) { Text("sign in") }
                else if (problem != UpdateViewerMessage) TextButton(onClick = { if (retry != null) retry() else attempt++ }) { Text("retry") }
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
