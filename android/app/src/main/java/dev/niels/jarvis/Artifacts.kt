package dev.niels.jarvis

import android.app.Activity
import android.content.ClipData
import android.content.ClipboardManager
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.unit.dp
import java.io.IOException
import java.time.DateTimeException
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

private fun publicationDate(value: String?, timezone: String): String? = value?.let {
    try {
        DateTimeFormatter.ofPattern("MMM d, yyyy", Locale.getDefault())
            .withZone(ZoneId.of(timezone)).format(Instant.parse(it))
    } catch (error: DateTimeException) {
        throw IOException("invalid publication date", error)
    }
}

private data class ShelfItem(
    val pin: DiscussionRef.Artifact, val title: String, val description: String?, val count: Int, val lastPublished: String?,
)

private suspend fun HomeApi.shelf(): List<ShelfItem> {
    val page = read("/api/artifacts") ?: throw IOException("library unavailable")
    val timezone = page.getString("timezone")
    return page.getJSONArray("items").objects().map {
        ShelfItem(DiscussionRef.Artifact(it.getString("slug"), it.getString("current")), it.getString("title"),
            it.string("description"), it.getInt("edition_count"), publicationDate(it.string("last_published_at"), timezone))
    }
}

private data class Edition(
    val ref: DiscussionRef.Artifact, val title: String, val description: String?, val change: String?,
    val date: String?, val current: Boolean,
)

private data class Work(val editions: List<Edition>) {
    fun label(edition: Edition): String {
        val siblings = editions.filter { it.date == edition.date && it != edition }
        val revision = edition.ref.revision
        val prefixSize = siblings.maxOfOrNull { revision.commonPrefixWith(it.ref.revision).length + 1 } ?: 0
        return listOfNotNull(
            edition.date,
            if (edition.date == null || siblings.isNotEmpty()) "edition " + revision.take(maxOf(8, prefixSize)) else null,
            if (edition.current) "current" else null,
        ).joinToString(" · ")
    }
}

private suspend fun HomeApi.work(slug: String): Work? {
    val data = read("/api/artifacts/$slug") ?: return null
    val current = data.getString("current")
    val timezone = data.getString("timezone")
    return Work(data.getJSONArray("editions").objects().map {
        val revision = it.getString("rev")
        Edition(DiscussionRef.Artifact(slug, revision), it.getString("title"), it.string("description"),
            it.string("change"), publicationDate(it.string("published_at"), timezone), revision == current)
    })
}

@Composable
internal fun ArtifactShelf(api: HomeApi, reload: Pair<Int, Int>, signIn: () -> Unit, navigate: (Route) -> Unit) {
    var expanded by rememberSaveable { mutableStateOf<String?>(null) }
    Read("artifacts", reload, signIn, api::shelf) { works ->
        if (works == null) return@Read
        LazyColumn(contentPadding = PaddingValues(20.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            item { Heading("artifacts") }
            if (works.isEmpty()) item { Text("no published artifacts") }
            items(works, key = { it.pin.slug }) { work ->
                val slug = work.pin.slug
                TextButton(onClick = { navigate(work.pin.route()) }, modifier = Modifier.fillMaxWidth()) {
                    Column(Modifier.fillMaxWidth()) {
                        Text(work.title, style = MaterialTheme.typography.titleMedium)
                        Text("current edition " + work.pin.revision.take(12), style = MaterialTheme.typography.labelMedium)
                    }
                }
                work.description?.let { Text(it) }
                work.lastPublished?.let { BodyStatus("last published $it") }
                if (work.count > 1) {
                    val open = expanded == slug
                    TextButton(
                        onClick = { expanded = if (open) null else slug },
                        modifier = Modifier.semantics { stateDescription = if (open) "expanded" else "collapsed" },
                    ) { Text("${work.count} editions of ${work.title}") }
                    if (open) Read(slug, reload, signIn, { api.work(slug) }) { detail ->
                        if (detail == null) BodyStatus("this work is no longer available")
                        else for (edition in detail.editions) {
                            TextButton(onClick = { navigate(edition.ref.route()) }, modifier = Modifier.fillMaxWidth()) {
                                Column(Modifier.fillMaxWidth()) {
                                    Text(edition.title)
                                    Text(detail.label(edition))
                                    edition.change?.let { Text(it) }
                                }
                            }
                        }
                    }
                }
                HorizontalDivider()
            }
        }
    }
}

@Composable
internal fun ArtifactPane(
    route: Route.Artifact, api: HomeApi, reload: Pair<Int, Int>, signIn: () -> Unit, activity: Activity,
    resolve: (Route) -> Unit, navigate: (Route) -> Unit, discuss: (DiscussionRef?) -> Unit,
) {
    var opened by rememberSaveable { mutableStateOf(false) }
    var browserError by rememberSaveable { mutableStateOf(false) }
    Read(route.slug, reload, signIn, { api.work(route.slug) }) { work ->
        Pane {
            val current = work?.editions?.find { it.current }
            if (route.revision == null && current != null) {
                LaunchedEffect(current.ref) { resolve(current.ref.route()) }
                BodyStatus("opening current edition")
                return@Pane
            }
            val edition = work?.editions?.find { it.ref.revision == route.revision }
            if (work == null || edition == null) {
                BodyStatus("this edition is no longer available")
                return@Pane
            }
            val pin = edition.ref.route()
            val open = { browserError = !Routes.openInBrowser(activity, pin) }
            LaunchedEffect(pin) {
                if (!opened) {
                    opened = true
                    open()
                }
            }
            Heading(edition.title)
            Text(work.label(edition))
            edition.description?.let { Text(it) }
            edition.change?.let { Text(it) }
            if (browserError) BodyStatus("browser unavailable")
            TextButton(onClick = open) { Text(if (browserError) "retry opening this edition in browser" else "open this edition in browser") }
            TextButton(onClick = {
                activity.getSystemService(ClipboardManager::class.java)
                    .setPrimaryClip(ClipData.newPlainText(edition.title, Routes.url(pin).toString()))
            }) { Text("copy edition link") }
            if (current != null && !edition.current) TextButton(onClick = { navigate(current.ref.route()) }) { Text("open current edition") }
            TextButton(onClick = { discuss(edition.ref) }) { Text("discuss this edition") }
            val path = "/api/artifacts/" + route.slug + "/" + edition.ref.revision + "/discussion"
            Read(path, reload, signIn, { api.read(path) }) { delivery ->
                delivery?.string("message_id")?.takeIf(::canonicalUuid)?.let { id ->
                    TextButton(onClick = { navigate(Route.Message(id)) }) { Text("open chat message") }
                }
            }
        }
    }
}
