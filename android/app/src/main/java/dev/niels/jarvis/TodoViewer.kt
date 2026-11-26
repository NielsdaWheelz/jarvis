package dev.niels.jarvis

import android.content.ClipData
import android.content.ClipboardManager
import android.net.Uri
import androidx.compose.foundation.interaction.DragInteraction
import androidx.compose.foundation.focusable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.layout.boundsInWindow
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.unit.dp
import java.io.IOException
import java.time.Instant
import org.json.JSONObject

internal class TodoReads {
    val index = ReadState<JSONObject>()
    val records = mutableMapOf<String, ReadState<JSONObject>>()
    val results = mutableMapOf<String, ReadState<JSONObject>>()
}

private fun completeIndex(page: JSONObject?): JSONObject {
    val response = page ?: throw IOException("missing todo list")
    val items = response.getJSONArray("items")
    val ids = HashSet<String>()
    for (i in 0 until items.length()) {
        val id = items.getJSONObject(i).getString("id")
        if (!canonicalUuid(id) || !ids.add(id)) throw IOException("invalid todo id")
    }
    if (response.get("offset") != 0 || response.get("total") != ids.size) {
        throw IOException("incomplete todo list")
    }
    return response
}

@Composable
internal fun TodoViewer(
    exact: String?, reads: TodoReads, api: HomeApi, reload: Pair<Int, Int>, signIn: () -> Unit,
    navigate: (Route) -> Unit, discuss: (DiscussionRef?) -> Unit,
) {
    var open by rememberSaveable { mutableStateOf(ArrayList(listOfNotNull(exact))) }
    var cursors by rememberSaveable { mutableStateOf(HashMap<String, String>()) }
    val indexPath = "/api/todos?all=true"
    reads.index.load(indexPath, reload) { completeIndex(api.read(indexPath)) }
    val page = reads.index.data
    val summaries = remember(page) { page?.objects("items").orEmpty().associateBy { it.getString("id") } }

    for (id in (open + listOfNotNull(exact)).distinct()) key(id) {
        val path = "/api/todos/$id"
        val record = reads.records.getOrPut(id, ::ReadState)
        record.load(path, reload) { api.read(path) }
        if (id in open && !(record.received && record.data == null)) {
            val resultsPath = "$path/results" + (cursors[id]?.let { "?before=${Uri.encode(it)}" } ?: "")
            reads.results.getOrPut(id, ::ReadState).load(resultsPath, reload) {
                api.read(resultsPath) ?: throw IOException("results unavailable")
            }
        }
    }

    val direct = reads.records[exact]
    val record = direct?.data?.optJSONObject("record")
    val gone = direct?.received == true && record == null
    val pinned = exact != null && (exact !in summaries || gone || record?.string("state") in setOf("done", "cancelled"))
    val resultRows = mutableMapOf<String, JSONObject>()
    val keys = buildList<String> {
        fun addTodo(id: String) {
            add(id)
            val detail = reads.records[id]
            if (id !in open || (detail?.received == true && detail.data == null)) return
            for (result in reads.results[id]?.data?.objects("items").orEmpty()) {
                val row = "$id/${result.getString("message_id")}"
                add(row)
                resultRows[row] = result
            }
        }
        add("heading")
        if (exact != null && pinned) addTodo(exact)
        var previous = ""
        for ((id, summary) in summaries) {
            if (pinned && id == exact) continue
            val section = summary.getString("section")
            if (section != previous) add("section/$section")
            previous = section
            addTodo(id)
        }
        add("checked")
    }

    // the server order may change while another destination is on top.
    // keep the key and its pixel offset as the visit's saved scroll position.
    val list = rememberLazyListState()
    var anchor by rememberSaveable { mutableStateOf(exact ?: "heading") }
    var offset by rememberSaveable { mutableIntStateOf(0) }
    var focus by rememberSaveable { mutableStateOf<String?>(null) }
    var pendingFocus by remember { mutableStateOf(focus) }
    var oldKeys by remember { mutableStateOf(emptyList<String>()) }
    var restoring by remember { mutableStateOf(true) }
    var anchorRank by rememberSaveable { mutableIntStateOf(0) }
    var focusRank by rememberSaveable { mutableIntStateOf(0) }
    fun nearest(removed: String, rank: Int): String {
        val pos = oldKeys.indexOf(removed)
        if (pos < 0) return summaries.keys.elementAtOrNull(rank.coerceAtMost(summaries.size - 1)) ?: "heading"
        for (distance in 1..oldKeys.size) {
            for (i in listOf(pos + distance, pos - distance)) {
                val id = oldKeys.getOrNull(i)
                if (id != null && (id in summaries || id in resultRows)) return id
            }
        }
        return "heading"
    }
    // a saved result may arrive after the index and its todo summary.
    val anchorOwner = anchor.substringBefore('/')
    val anchorContentReady = anchorOwner !in open || (anchorOwner != exact && anchorOwner !in summaries) ||
        (anchor == anchorOwner && offset == 0) ||
        (reads.records[anchorOwner]?.settled == true && (reads.results[anchorOwner]?.settled == true ||
            reads.records[anchorOwner]?.data == null))
    val directAnchorReady = anchorOwner == exact && anchor in keys && (anchor != exact || offset > 0)
    SideEffect {
        if ((page != null || directAnchorReady) && (oldKeys != keys || restoring) && (!restoring || anchorContentReady)) {
            if (anchor !in keys) {
                anchor = if (anchorOwner in keys) anchorOwner else nearest(anchor, anchorRank)
                offset = 0
            }
            list.requestScrollToItem(keys.indexOf(anchor), offset)
            focus?.let { control ->
                val owner = control.substringBefore('/')
                val missingResult = control != owner && canonicalUuid(control.substringAfter('/')) &&
                    reads.results[owner]?.received == true && control !in keys
                if ((page != null && owner !in keys) || missingResult) {
                    focus = if (owner in keys) owner else nearest(owner, focusRank)
                    pendingFocus = focus
                }
            }
            restoring = false
            oldKeys = keys
        }
        if (page != null) {
            val valid = summaries.keys + listOfNotNull(exact)
            if (open.any { it !in valid }) open = ArrayList(open.filter { it in valid })
            if (cursors.keys.any { it !in valid }) cursors = HashMap(cursors.filterKeys { it in valid })
            reads.records.keys.retainAll(valid)
            reads.results.keys.retainAll(valid)
        }
    }
    LaunchedEffect(list) {
        list.interactionSource.interactions.collect {
            if (it is DragInteraction.Start) {
                restoring = false
                pendingFocus = null
            }
        }
    }
    LaunchedEffect(list, keys, restoring) {
        if (!restoring) snapshotFlow {
            val first = list.layoutInfo.visibleItemsInfo.firstOrNull { it.index == list.firstVisibleItemIndex }
            (first?.key as? String) to list.firstVisibleItemScrollOffset
        }.collect { (id, pixels) ->
            if (id != null && id in keys) {
                anchor = id
                val rank = summaries.keys.indexOf(id.substringBefore('/'))
                if (rank >= 0) anchorRank = rank
                offset = pixels
            }
        }
    }
    val rememberFocus: (String) -> Unit = {
        focus = it
        val rank = summaries.keys.indexOf(it.substringBefore('/'))
        if (rank >= 0) focusRank = rank
    }
    val restored = { pendingFocus = null }
    val restoreFocus = pendingFocus.takeUnless { restoring }
    val context = LocalContext.current
    LazyColumn(state = list, contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
        items(keys, key = { it }) { id ->
            when {
                id == "heading" -> Column {
                    Column(controlFocus(id, restoreFocus, rememberFocus, restored).focusable()) { Heading("todos") }
                    reads.index.status(signIn)
                    if (page != null && summaries.isEmpty()) Text("no active todos")
                }
                id == "checked" -> page?.let { BodyStatus("checked ${formattedTime(it.string("as_of"), it.string("timezone"))}") }
                id.startsWith("section/") -> Section(id.substringAfter('/').replace('_', ' '))
                id in resultRows -> {
                    val result = resultRows.getValue(id)
                    val zone = reads.records[id.substringBefore('/')]?.data?.string("timezone")
                    TextButton(onClick = {
                        rememberFocus(id)
                        navigate(Route.Message(result.getString("message_id")))
                    }, modifier = controlFocus(id, restoreFocus, rememberFocus, restored).padding(start = 16.dp)) {
                        Column(Modifier.fillMaxWidth()) {
                            Text(result.getString("label").ifBlank { "open result" })
                            Text(formattedTime(result.string("at"), zone), style = MaterialTheme.typography.labelMedium)
                        }
                    }
                }
                else -> Column {
                    val detail = reads.records[id]
                    val item = if (pinned && id == exact) record ?: summaries[id] else summaries[id]
                    if (detail?.received == true && detail.data == null && (id == exact || id in open)) {
                        BodyStatus("this todo is no longer available")
                        detail.status(signIn)
                    } else if (item == null) {
                        detail?.status(signIn)
                    } else {
                        val expanded = id in open
                        val section = if (pinned && id == exact) null else item.string("section")
                        val label = listOfNotNull(
                            item.string("due_date")?.let { due ->
                                val today = page?.string("today")
                                val prefix = when {
                                    item.string("state") in setOf("done", "cancelled") -> "due"
                                    today != null && due < today -> "overdue"
                                    due == today -> "due today"
                                    else -> "due"
                                }
                                "$prefix · ${civilDate(due)}"
                            },
                            item.string("state")?.takeIf { it != section }?.replace('_', ' '),
                        ).joinToString(" · ")
                        TextButton(
                            onClick = {
                                rememberFocus(id)
                                open = ArrayList(if (expanded) open - id else open + id)
                            },
                            modifier = controlFocus(id, restoreFocus, rememberFocus, restored)
                                .fillMaxWidth().semantics { stateDescription = if (expanded) "expanded" else "collapsed" },
                        ) {
                            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                Text(if (expanded) "▾" else "▸")
                                Column {
                                    Text(item.getString("title"), style = MaterialTheme.typography.titleMedium)
                                    if (label.isNotEmpty()) Text(label, style = MaterialTheme.typography.labelMedium)
                                }
                            }
                        }
                        if (expanded) Column(Modifier.padding(start = 16.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                            detail?.status(signIn)
                            val data = detail?.data
                            val todo = data?.optJSONObject("record")
                            val zone = data?.string("timezone")
                            if (todo != null) {
                                Prose(todo.getString("content"), navigate)
                                todo.string("wake_at")?.let {
                                    val past = Instant.parse(it) <= Instant.parse(data.getString("as_of"))
                                    Text("jarvis check ${if (past) "was due" else "scheduled for"} ${formattedTime(it, zone)}")
                                }
                                BodyStatus("checked ${formattedTime(data.string("as_of"), zone)}")
                            }
                            TextButton(onClick = {
                                rememberFocus("$id/link")
                                context.getSystemService(ClipboardManager::class.java)
                                    .setPrimaryClip(ClipData.newPlainText("todo", Routes.url(Route.Todo(id)).toString()))
                            }, modifier = controlFocus("$id/link", restoreFocus, rememberFocus, restored)) { Text("copy todo link") }
                            TextButton(onClick = {
                                rememberFocus("$id/discuss")
                                discuss(DiscussionRef.Todo(id))
                            }, modifier = controlFocus("$id/discuss", restoreFocus, rememberFocus, restored)) { Text("discuss this todo") }
                            val results = reads.results[id]
                            results?.status(signIn)
                            val entries = results?.data?.objects("items").orEmpty()
                            if (entries.isNotEmpty() || id in cursors) Section("linked results")
                            results?.data?.string("next_before")?.let { edge ->
                                TextButton(onClick = { cursors = HashMap(cursors).apply { put(id, edge) } }) { Text("earlier results") }
                            }
                            if (id in cursors) TextButton(onClick = { cursors = HashMap(cursors).apply { remove(id) } }) { Text("latest results") }
                        }
                    }
                    HorizontalDivider()
                }
            }
        }
    }
}

@Composable
private fun controlFocus(id: String, pending: String?, focused: (String) -> Unit, restored: () -> Unit): Modifier {
    val requester = remember { FocusRequester() }
    var visible by remember { mutableStateOf(false) }
    LaunchedEffect(id, pending, visible) {
        if (pending == id && visible) {
            requester.requestFocus()
            restored()
        }
    }
    return Modifier
        .onGloballyPositioned { visible = !it.boundsInWindow().isEmpty }
        .focusRequester(requester)
        .onFocusChanged { if (it.isFocused) focused(id) }
}
