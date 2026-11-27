package dev.niels.jarvis

import android.content.Context
import android.net.Uri
import java.io.IOException
import java.util.concurrent.TimeUnit
import kotlin.coroutines.resumeWithException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import okhttp3.Call
import okhttp3.Callback
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import okio.BufferedSink
import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject

internal class DriveFailure(val code: String, val retryAfter: String?) : IOException(code)

internal const val UpdateViewerMessage = "update jarvis to continue"
internal class ViewerUpdateRequired : IOException(UpdateViewerMessage)

internal class SignInRequired : IOException("sign in to continue")

internal class HomeApi(context: Context) {
    private val application = context.applicationContext
    private val access = Access.get(context)

    suspend fun request(
        path: String,
        method: String = "GET",
        body: RequestBody? = null,
        headers: Map<String, String> = emptyMap(),
        retryAuthentication: Boolean = true,
        timeoutMillis: Long? = null,
    ): Response {
        require(path.startsWith("/api/"))
        val url = requireNotNull(origin.resolve(path))
        require(url.host == origin.host && url.scheme == origin.scheme && url.port == origin.port && url.encodedPath.startsWith("/api/"))
        val payload = body?.let { source ->
            object : RequestBody() {
                override fun contentType() = source.contentType()
                override fun contentLength() = source.contentLength()
                override fun writeTo(sink: BufferedSink) = source.writeTo(sink)
                override fun isOneShot() = true
            }
        }
        val request = Request.Builder().url(url).method(method, payload)
        for ((name, value) in headers) request.header(name, value)
        request.header("Cache-Control", "no-store")
        request.header("X-Jarvis-Viewer-Contract", "shown-v1")
        if (method != "GET" && method != "HEAD") request.header("Origin", Routes.origin)
        if (method == "PUT" && url.pathSegments.size == 3 && url.pathSegments[1] == "messages") {
            ShownReports.get(application).flush()
        }
        var bearer = access.currentBearer() ?: throw SignInRequired()
        var response = execute(request.header("Authorization", "Bearer $bearer").build(), timeoutMillis)
        val report = method == "POST" && path in setOf("/api/shown", "/api/shown/clear")
        if (retryAuthentication && response.code == 401 && (method == "GET" || method == "HEAD" || report)) {
            response.close()
            access.rejectedBearer(bearer)
            bearer = access.currentBearer() ?: throw SignInRequired()
            response = execute(request.header("Authorization", "Bearer $bearer").build(), timeoutMillis)
        }
        if (response.isRedirect || response.code == 401 || response.code == 403) {
            response.close()
            access.rejectedBearer(bearer)
            throw SignInRequired()
        }
        return response
    }

    private suspend fun execute(request: Request, timeoutMillis: Long?): Response = suspendCancellableCoroutine { continuation ->
        val transport = if (request.method == "GET" || request.method == "HEAD") reads else client
        val call = transport.newCall(request)
        timeoutMillis?.let { call.timeout().timeout(it, TimeUnit.MILLISECONDS) }
        continuation.invokeOnCancellation { call.cancel() }
        call.enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) = continuation.resumeWithException(e)
            override fun onResponse(call: Call, response: Response) {
                continuation.resume(response) { _, unclaimed, _ -> unclaimed.close() }
            }
        })
    }

    suspend fun read(path: String, timeoutMillis: Long? = null): JSONObject? = withContext(Dispatchers.IO) {
        request(path, timeoutMillis = timeoutMillis).use { response ->
            when {
                response.code == 426 -> throw ViewerUpdateRequired()
                response.code == 404 -> null
                response.isSuccessful -> response.json()
                else -> throw IOException("could not load this item")
            }
        }
    }

    suspend fun writeShown(path: String, data: JSONObject) {
        request(path, "POST", data.toString().toRequestBody("application/json".toMediaType()), timeoutMillis = 3_000)
            .use { response ->
                when (response.code) {
                    204 -> Unit
                    426 -> throw ViewerUpdateRequired()
                    else -> throw IOException("could not save shown messages")
                }
            }
    }

    suspend fun selectedHome(): DiscussionRef.Artifact? {
        val data = read("/api/home") ?: throw IOException("home unavailable")
        val view = data.get("view")
        if (view == JSONObject.NULL) return null
        return DiscussionRef.parse(view as? JSONObject) as? DiscussionRef.Artifact
            ?: throw IOException("invalid home selection")
    }

    suspend fun drive(path: String): JSONObject = withContext(Dispatchers.IO) {
        request(path).use { response ->
            response.checkDrive()
            response.json()
        }
    }

    suspend fun pendingUploads(): List<JSONObject> = withContext(Dispatchers.IO) {
        request("/api/drive/pending").use { response ->
            response.checkDrive()
            try {
                JSONArray(response.body?.string() ?: throw IOException("missing response")).objects()
            } catch (error: JSONException) {
                throw IOException("invalid response", error)
            }
        }
    }

    private companion object {
        val origin = Routes.origin.toHttpUrl()
        val client = OkHttpClient.Builder()
            .followRedirects(false)
            .retryOnConnectionFailure(false)
            .readTimeout(45, TimeUnit.SECONDS)
            .writeTimeout(45, TimeUnit.SECONDS)
            .build()
        // A stale pooled connection can be retried only for an idempotent read.
        val reads = client.newBuilder().retryOnConnectionFailure(true).build()
    }
}

internal fun Response.checkDrive() {
    if (!isSuccessful) {
        val code = try { json().string("detail") } catch (_: IOException) { null }
        throw DriveFailure(code ?: "drive_unavailable", header("Retry-After"))
    }
}

internal fun Response.json(): JSONObject = try {
    JSONObject(body?.string() ?: throw IOException("missing response"))
} catch (e: JSONException) {
    throw IOException("invalid response", e)
}

internal fun JSONObject.string(key: String): String? = opt(key) as? String

internal fun JSONObject.objects(key: String): List<JSONObject> = optJSONArray(key).objects()

internal fun JSONArray?.objects(): List<JSONObject> =
    if (this == null) emptyList() else List(length()) { getJSONObject(it) }

internal sealed interface DiscussionRef {
    fun json(): JSONObject
    fun route(): Route
    val label: String

    data class Todo(val id: String) : DiscussionRef {
        override fun json() = JSONObject().put("kind", "todo").put("id", id)
        override fun route() = Route.Todo(id)
        override val label = "todo"
    }

    data class Proposal(val messageId: String, val actionId: String) : DiscussionRef {
        override fun json() = JSONObject().put("kind", "proposal")
            .put("message_id", messageId).put("action_id", actionId)
        override fun route() = Route.Message(messageId)
        override val label = "proposal"
    }

    data class File(val id: String, val page: Long?) : DiscussionRef {
        override fun json() = JSONObject().put("kind", "file").put("id", id).apply {
            page?.let { put("page", it) }
        }
        override fun route() = Route.File(id, page)
        override val label = if (page == null) "original file" else "page $page"
    }

    data class DriveFile(val subject: String, val id: String, val page: Long?) : DiscussionRef {
        override fun json() = JSONObject().put("kind", "drive_file").put("subject", subject)
            .put("id", id).apply { page?.let { put("page", it) } }
        override fun route() = Route.DriveFile(subject, id, page)
        override val label = if (page == null) "drive file" else "page $page"
    }

    data class Artifact(val slug: String, val revision: String) : DiscussionRef {
        override fun json() = JSONObject().put("kind", "view").put("slug", slug).put("rev", revision)
        override fun route() = Route.Artifact(slug, revision)
        override val label get() = labelAmong(emptyList())

        fun labelAmong(others: List<Artifact>): String {
            val prefix = others.asSequence().filter { it.slug == slug && it != this }
                .maxOfOrNull { revision.commonPrefixWith(it.revision).length + 1 } ?: 0
            return "${slug.replace('-', ' ')} · edition ${revision.take(maxOf(12, prefix))}"
        }
    }

    companion object {
        fun parse(value: JSONObject?): DiscussionRef? = when (value?.string("kind")) {
            "todo" -> Todo(value.getString("id"))
            "proposal" -> Proposal(value.getString("message_id"), value.getString("action_id"))
            "file" -> File(value.getString("id"), (value.opt("page") as? Number)?.toLong())
            "drive_file" -> DriveFile(value.getString("subject"), value.getString("id"), (value.opt("page") as? Number)?.toLong())
            "view" -> Artifact(value.getString("slug"), value.getString("rev"))
            else -> null
        }
    }
}

internal fun hrefRoute(value: String): Route? = Routes.parse(
    Uri.parse(if (value.startsWith("/")) Routes.origin + value else value),
)
