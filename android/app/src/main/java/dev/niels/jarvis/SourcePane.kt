package dev.niels.jarvis

import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
import android.widget.Toast
import androidx.compose.foundation.relocation.BringIntoViewRequester
import androidx.compose.foundation.relocation.bringIntoViewRequester
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextLayoutResult
import androidx.compose.ui.text.buildAnnotatedString
import androidx.lifecycle.compose.LifecycleResumeEffect
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.withTimeout
import org.json.JSONObject
import java.io.IOException

@Composable
internal fun SourcePane(route: Route.Source, api: HomeApi, refresh: Int, auth: Int, navigate: (Route) -> Unit, back: (() -> Unit)?) {
    val context = LocalContext.current
    var visible by remember { mutableStateOf(false) }
    var visit by remember { mutableIntStateOf(0) }
    var source by remember(route, auth) { mutableStateOf<JSONObject?>(null) }
    var failure by remember(route, auth) { mutableStateOf(false) }
    var retry by remember { mutableIntStateOf(0) }
    LifecycleResumeEffect(route, auth) {
        visible = true
        onPauseOrDispose {
            visit++
            visible = false
            source = null
            failure = false
        }
    }
    LaunchedEffect(route, refresh, auth, visit, visible, retry) {
        if (!visible) return@LaunchedEffect
        val requestVisit = visit
        try {
            val result = withTimeout(15_000) { api.read("/api/messages/${route.reply}/sources/${route.slot}") }
                ?: JSONObject().put("state", "unavailable")
            if (!visible || visit != requestVisit) return@LaunchedEffect
            source = result
            failure = false
        } catch (_: TimeoutCancellationException) {
            source = null
            failure = true
        } catch (error: CancellationException) {
            throw error
        } catch (_: IOException) {
            source = null
            failure = true
        }
    }
    Pane {
        val data = source
        if (failure || data?.string("state") == "unavailable") {
            BodyStatus(if (failure) "could not check source" else "source unavailable")
            TextButton(onClick = { retry++ }) { Text("retry") }
        } else if (visible && data?.string("state") == "available") {
            val coverage = data.getJSONObject("coverage")
            val kind = data.getString("kind")
            Heading(when (coverage.getString("kind")) {
                "preview" -> "email preview"
                "event" -> "calendar occurrence"
                else -> "email excerpt"
            })
            Text("observed " + formattedTime(data.getString("observed_at"), "UTC"))
            for (field in data.objects("fields")) {
                SelectionContainer { Text(field.getString("label") + " · " + field.getString("value")) }
            }
            if (coverage.string("passage") == "missing") BodyStatus("exact passage unavailable")
            val omissions = coverage.optJSONArray("omissions")
            for (i in 0 until (omissions?.length() ?: 0)) BodyStatus(omissions!!.getString(i))
            val focus = data.optJSONObject("focus")
            data.objects("segments").forEach { segment ->
                key(segment.getString("part"), segment.getString("digest"), segment.getInt("start")) {
                    if (segment.string("observed_at") != data.string("observed_at"))
                        Text("observed " + formattedTime(segment.string("observed_at"), "UTC"))
                    SourceSegment(segment, focus)
                }
            }
            data.string("original_url")?.let(Uri::parse)?.takeIf {
                it.scheme == "https" && it.userInfo == null &&
                    it.host == (if (kind == "mail") "mail.google.com" else "calendar.google.com")
            }?.let { uri ->
                TextButton(onClick = {
                    try { context.startActivity(Intent(Intent.ACTION_VIEW, uri)) }
                    catch (_: ActivityNotFoundException) { Toast.makeText(context, "browser unavailable", Toast.LENGTH_SHORT).show() }
                }) { Text(if (kind == "mail") "open current in gmail" else "open current in calendar") }
            }
        } else if (visible) CircularProgressIndicator()
        TextButton(onClick = back ?: { navigate(Route.Message(route.reply)) }) { Text("back to message") }
    }
}

@Composable
private fun SourceSegment(segment: JSONObject, focus: JSONObject?) {
    val text = segment.getString("text")
    val start = segment.getInt("start")
    val end = segment.getInt("end")
    val bytes = remember(text) { text.toByteArray(Charsets.UTF_8) }
    val range = focus?.takeIf { it.string("part") == segment.string("part") && it.string("digest") == segment.string("digest") }
        ?.let {
            val from = maxOf(start, it.getInt("start"))
            val to = minOf(end, it.getInt("end"))
            if (from >= to || end - start != bytes.size) null
            else bytes.decodeToString(0, from - start).length until bytes.decodeToString(0, to - start).length
        }
    val highlighted = buildAnnotatedString {
        append(text)
        if (range != null && !range.isEmpty()) addStyle(SpanStyle(background = MaterialTheme.colorScheme.tertiaryContainer), range.first, range.last + 1)
    }
    val bring = remember { BringIntoViewRequester() }
    var layout by remember { mutableStateOf<TextLayoutResult?>(null) }
    var positioned by rememberSaveable { mutableStateOf(false) }
    SelectionContainer {
        Text(highlighted, Modifier.bringIntoViewRequester(bring), onTextLayout = { layout = it })
    }
    LaunchedEffect(layout, range) {
        if (!positioned && range != null && !range.isEmpty() && focus?.getInt("start") in start until end) {
            val bounds: Rect = layout?.getBoundingBox(range.first) ?: return@LaunchedEffect
            bring.bringIntoView(bounds)
            positioned = true
        }
    }
}
