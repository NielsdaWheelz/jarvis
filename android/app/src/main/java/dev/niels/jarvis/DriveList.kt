package dev.niels.jarvis

import android.net.Uri
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.unit.dp
import java.io.IOException
import org.json.JSONException
import org.json.JSONObject

private class DirectoryVisit {
    var rows by mutableStateOf<List<JSONObject>>(emptyList())
    var cursor by mutableStateOf<String?>(null)
    var error by mutableStateOf<IOException?>(null)
    var loading by mutableStateOf(false)
    var partial by mutableStateOf(false)
    var depth by mutableIntStateOf(0)
    var subject by mutableStateOf<String?>(null)
    var locations by mutableStateOf<Map<String, String>>(emptyMap())
}

@Composable
internal fun DriveList(
    folder: JSONObject?,
    api: HomeApi,
    reload: Pair<Int, Int>,
    signIn: () -> Unit,
    navigate: (Route) -> Unit,
    attach: (DiscussionRef) -> Unit,
    subject: String? = null,
) {
    var input by rememberSaveable { mutableStateOf("") }
    var search by rememberSaveable { mutableStateOf("") }
    var recent by rememberSaveable { mutableStateOf(false) }
    var selected by rememberSaveable { mutableStateOf<String?>(null) }
    var selectedIndex by rememberSaveable { mutableIntStateOf(0) }
    var selectedOffset by rememberSaveable { mutableIntStateOf(0) }
    val restoring = remember { selected }
    val folderId = folder?.string("id")
    val selector = when {
        search.isNotEmpty() -> "q=${Uri.encode(search)}"
        recent -> "recent=true"
        else -> "folder=${folderId ?: "root"}"
    }
    key(selector) {
        val scroll = rememberLazyListState()
        fun open(route: Route, id: String? = null) {
            selected = id
            selectedIndex = scroll.firstVisibleItemIndex
            selectedOffset = scroll.firstVisibleItemScrollOffset
            navigate(route)
        }
        var depth by rememberSaveable { mutableIntStateOf(1) }
        var attempt by remember { mutableIntStateOf(0) }
        var restart by remember { mutableIntStateOf(0) }
        val directory = remember(reload, restart) { DirectoryVisit() }
        LaunchedEffect(directory, depth, attempt) {
            directory.loading = true
            directory.error = null
            try {
                while (directory.depth < depth) {
                    val cursor = directory.cursor
                    if (directory.depth > 0 && cursor == null) break
                    val path = "/api/drive/files?$selector" + (cursor?.let { "&cursor=${Uri.encode(it)}" } ?: "")
                    val page = api.drive(path)
                    val owner = page.getString("subject")
                    if (subject != null && owner != subject) throw DriveFailure("drive_inaccessible", null)
                    directory.subject = owner
                    directory.rows = (directory.rows + page.objects("items")).distinctBy { it.getString("id") }
                    directory.partial = directory.partial || page.getString("coverage") == "partial"
                    directory.cursor = page.string("next")
                    directory.depth++
                }
            } catch (error: IOException) {
                directory.error = error
            } catch (_: JSONException) {
                directory.error = IOException("invalid response")
            } finally {
                directory.loading = false
            }
        }
        val pending by produceState<List<JSONObject>?>(null, selector, reload) {
            value = if (selector == "folder=root") {
                try { api.pendingUploads() } catch (_: IOException) { null }
            } else null
        }
        LaunchedEffect(restoring, directory.depth, pending) {
            if (restoring != null && selected == restoring &&
                (directory.rows.any { it.string("id") == restoring } ||
                    pending.orEmpty().any { it.string("id") == restoring })
            ) {
                val count = 2 + directory.rows.size + (pending?.size ?: 0) +
                    if (pending.isNullOrEmpty()) 0 else 1
                scroll.scrollToItem(selectedIndex.coerceAtMost(count - 1), selectedOffset)
            }
        }
        val nameCounts = directory.rows.groupingBy { it.getString("name") }.eachCount()
        val parentIds = directory.rows.mapNotNull {
            it.string("parent").takeIf { _ -> (nameCounts[it.getString("name")] ?: 0) > 1 }
        }.distinct()
        val listingSubject = directory.subject
        LaunchedEffect(directory, listingSubject, parentIds) {
            if (listingSubject != null) for (parent in parentIds) {
                if (parent in directory.locations) continue
                val location = try {
                    val result = api.drive("/api/drive/$listingSubject/$parent")
                    val path = result.objects("trail").map { it.getString("name") } + result.getString("name")
                    path.joinToString(" / ")
                } catch (_: IOException) {
                    "location unavailable"
                } catch (_: JSONException) {
                    "location unavailable"
                }
                directory.locations = directory.locations + (parent to location)
            }
        }
        LazyColumn(
            state = scroll,
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(20.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            item("controls") {
                FlowRow(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    TextButton(onClick = {
                        if (folder == null) {
                            search = ""
                            input = ""
                            recent = false
                        } else open(Route.Files)
                    }) { Text("my drive") }
                    if (!recent && search.isEmpty() && subject != null) {
                        for (parent in folder?.objects("trail").orEmpty()) {
                            TextButton(onClick = { open(Route.DriveFile(subject, parent.getString("id"))) }) {
                                Text(parent.getString("name"))
                            }
                        }
                    }
                    TextButton(onClick = {
                        search = ""
                        input = ""
                        recent = true
                        selected = null
                    }) { Text("recent") }
                    if (folderId != null && subject != null && !recent && search.isEmpty()) {
                        TextButton(onClick = { attach(DiscussionRef.DriveFile(subject, folderId, null)) }) {
                            Text("attach to chat")
                        }
                    }
                }
                OutlinedTextField(
                    value = input,
                    onValueChange = { if (it.length <= 255) input = it },
                    modifier = Modifier.fillMaxWidth(),
                    label = { Text("search filenames") },
                    singleLine = true,
                )
                TextButton(enabled = input.isNotBlank(), onClick = {
                    search = input.trim()
                    recent = false
                    selected = null
                }) { Text("search") }
                Heading(when {
                    search.isNotEmpty() -> "search results"
                    recent -> "recent"
                    else -> folder?.string("name") ?: "my drive"
                })
            }
            if (!pending.isNullOrEmpty()) item("pending-title") { Section("pending uploads") }
            items(pending.orEmpty(), key = { "pending-" + it.getString("id") }) { row ->
                val id = row.getString("id")
                DriveRow(row.string("name") ?: "file", restoring == id && selected == id, { selected = null }, { open(Route.File(id, null), id) }) {
                    val date = formattedTime(row.string("received_at"))
                    Text(originStatus(row) + " · received $date", style = MaterialTheme.typography.bodySmall)
                }
            }
            val openedSubject = directory.subject
            if (openedSubject != null) {
                val locations = directory.rows.groupingBy { it.getString("name") to it.string("parent") }.eachCount()
                items(directory.rows, key = { it.getString("id") }) { item ->
                    val name = item.getString("name")
                    val id = item.getString("id")
                    val duplicate = (nameCounts[name] ?: 0) > 1
                    DriveRow(name, restoring == id && selected == id, { selected = null }, { open(Route.DriveFile(openedSubject, id), id) }) {
                        val parent = item.string("parent")
                        val location = if (duplicate) {
                            if (parent == null) "no accessible parent" else directory.locations[parent]
                        } else null
                        val details = listOfNotNull(
                            fileType(item.getString("mime")),
                            item.string("modified")?.let { formattedTime(it) },
                            location,
                            id.takeLast(8).takeIf { (locations[name to item.string("parent")] ?: 0) > 1 },
                        )
                        Text(details.joinToString(" · "), style = MaterialTheme.typography.bodySmall)
                    }
                }
            }
            item("status") {
                val error = directory.error
                when {
                    error != null -> DriveRetry(error, signIn) {
                        if (error is DriveFailure && error.code == "drive_cursor_stale") {
                            depth = 1
                            restart++
                        } else attempt++
                    }
                    directory.loading -> CircularProgressIndicator()
                    directory.partial -> BodyStatus("some locations could not be searched.")
                    directory.depth > 0 && directory.rows.isEmpty() && directory.cursor == null -> BodyStatus("no files found.")
                }
                if (directory.cursor != null && error == null)
                    TextButton(enabled = !directory.loading, onClick = { depth++ }) { Text("more files") }
            }
        }
    }
}

@Composable
private fun DriveRow(
    name: String,
    restore: Boolean,
    restored: () -> Unit,
    open: () -> Unit,
    metadata: @Composable () -> Unit,
) {
    val focus = remember { FocusRequester() }
    LaunchedEffect(restore) {
        if (restore) {
            focus.requestFocus()
            restored()
        }
    }
    Column {
        TextButton(onClick = open, modifier = Modifier.focusRequester(focus)) { Text(name) }
        metadata()
        HorizontalDivider()
    }
}

private fun fileType(mime: String): String = when (mime) {
    folderMime -> "folder"
    "application/pdf" -> "pdf"
    "application/vnd.google-apps.document" -> "google doc"
    "application/vnd.google-apps.spreadsheet" -> "google sheet"
    "application/vnd.google-apps.presentation" -> "google slides"
    else -> if (mime.startsWith("image/")) "image" else mime.substringAfterLast('/')
}
