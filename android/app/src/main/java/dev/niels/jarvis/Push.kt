package dev.niels.jarvis

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.service.notification.StatusBarNotification
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.app.NotificationCompat
import com.google.android.gms.tasks.Task
import com.google.firebase.FirebaseApp
import com.google.firebase.installations.FirebaseInstallations
import com.google.firebase.messaging.FirebaseMessaging
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import java.io.IOException
import java.nio.ByteBuffer
import java.security.MessageDigest
import java.util.UUID
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.filterNotNull
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.runInterruptible
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject

private const val PHONE = "/api/push/phone"
private const val REPLY = "reply"
private const val QUESTION = "question"
private const val WORKSPACE = "workspace_check"

private fun NotificationManager.prepareChannels() {
    createNotificationChannels(
        listOf(
            NotificationChannel(REPLY, "replies", NotificationManager.IMPORTANCE_DEFAULT),
            NotificationChannel(QUESTION, "questions", NotificationManager.IMPORTANCE_HIGH),
            NotificationChannel(WORKSPACE, "scheduled checks", NotificationManager.IMPORTANCE_HIGH)
        )
    )
}

class Push : FirebaseMessagingService() {
    override fun onRegistered(installationId: String) {
        PhoneAlerts.get(this).registered(installationId)
    }

    override fun onMessageReceived(message: RemoteMessage) {
        val data = message.data
        val notice = data["notice_id"]?.takeIf(::canonicalUuid) ?: return
        val kind = data["kind"] ?: return
        if (kind == WORKSPACE) {
            if (data.keys != setOf("kind", "notice_id", "todo_id")) return
            val todo = data["todo_id"]?.takeIf(::canonicalUuid) ?: return
            val manager = getSystemService(NotificationManager::class.java)
            if (!manager.allows(kind)) return
            val destination = Intent(this, WorkspaceTapActivity::class.java).setData(
                Uri.Builder().scheme("jarvis-check").authority("tap")
                    .appendPath(notice).appendPath(todo).build()
            )
            manager.notify(notice, 0, notification(this, kind, "open jarvis", destination).build())
            return
        }

        if (kind !in setOf(REPLY, QUESTION) || data.keys != setOf("kind", "notice_id", "message_id")) return
        val id = data["message_id"]?.takeIf(::canonicalUuid) ?: return
        if (notice == messageNoticeTag(id)) PhoneNotices.get(this).receive(id, kind)
    }
}

private fun NotificationManager.allows(kind: String): Boolean {
    if (!areNotificationsEnabled()) return false
    prepareChannels()
    return getNotificationChannel(kind)?.importance != NotificationManager.IMPORTANCE_NONE
}

private fun notification(context: Context, channel: String, title: String, destination: Intent) =
    NotificationCompat.Builder(context, channel)
        .setSmallIcon(R.drawable.ic_notification)
        .setContentTitle(title)
        .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
        .setAutoCancel(true)
        .setContentIntent(PendingIntent.getActivity(context, 0, destination, PendingIntent.FLAG_IMMUTABLE))

private fun messageNoticeTag(id: String): String {
    val namespace = UUID.fromString(id)
    val bytes = MessageDigest.getInstance("SHA-1").apply {
        update(ByteBuffer.allocate(16).putLong(namespace.mostSignificantBits).putLong(namespace.leastSignificantBits).array())
    }.digest("jarvis-home-notice:reply".toByteArray())
    bytes[6] = (bytes[6].toInt() and 15 or 80).toByte()
    bytes[8] = (bytes[8].toInt() and 63 or 128).toByte()
    val hash = ByteBuffer.wrap(bytes)
    return UUID(hash.long, hash.long).toString()
}

class NoticeDismissed : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        intent.data?.lastPathSegment?.let { PhoneNotices.get(context).dismissed(it) }
    }
}

internal class PhoneNotices private constructor(private val context: Context) {
    init { context.deleteSharedPreferences("chat-shown") }
    private val manager = context.getSystemService(NotificationManager::class.java)
    private val held = context.getSharedPreferences("held-chat-notices", Context.MODE_PRIVATE)
    private var startup = held.all.keys.toSet()
    private var foreground: Boolean? = null
    private var visibility = 0L
    private val postingReplies = mutableSetOf<String>()
    private var revision = 0L
    private val groupHandler = Handler(Looper.getMainLooper())
    private val reconcileGroup = Runnable { settleGroup() }
    private val issued = mutableMapOf<String, Long>()

    internal data class BeforeRead(val active: List<StatusBarNotification>, val revision: Long)

    @Synchronized
    fun foreground(visible: Boolean): Long {
        foreground = visible
        return ++visibility
    }

    @Synchronized
    fun waitingAtStartup() = startup.intersect(held.all.keys)

    @Synchronized
    fun finishStartup() {
        if (startup.isEmpty()) return
        val checked = startup
        startup = emptySet()
        if (foreground != true) postHeld(held.all.filterKeys { it in checked })
    }

    @Synchronized
    fun releaseHeld(departure: Long) {
        if (foreground == true || departure != visibility) return
        postHeld(held.all.filterKeys { it !in startup })
    }

    private fun postHeld(waiting: Map<String, *>) {
        for ((id, stored) in waiting) {
            post(id, (stored as String).substringBefore(' '))
            held.edit().remove(id).apply()
        }
        if (waiting.isNotEmpty()) updateGroup(replyTags().size)
    }

    @Synchronized
    fun revisionBeforeWrite() = revision

    @Synchronized
    fun confirmHeld(before: Long, ids: Collection<String>) {
        val matched = ids.filter { held.contains(it) && (issued[messageNoticeTag(it)] ?: 0L) <= before }
        if (matched.isEmpty()) return
        val edited = held.edit()
        matched.forEach(edited::remove)
        edited.commit()
    }

    @Synchronized
    fun receive(id: String, kind: String) {
        if (!manager.allows(kind)) return
        val tag = messageNoticeTag(id)
        issued[tag] = ++revision
        if (foreground == true) {
            if (held.edit().putString(id, kind).commit()) return
        }
        post(id, kind)
        if (kind == REPLY) updateGroup(replyTags().size)
    }

    @Synchronized
    fun snapshot(): BeforeRead {
        val active = manager.activeNotifications.toList()
        issued.keys.retainAll(active.mapTo(mutableSetOf()) { it.tag } + held.all.keys.map(::messageNoticeTag) + postingReplies)
        return BeforeRead(active, revision)
    }

    @Synchronized
    fun sweep(snapshot: BeforeRead, page: ChatPage) {
        val previous = snapshot.active.associateBy { it.tag }
        val active = manager.activeNotifications.associateBy { it.tag }
        val replies = replyTags()
        val shown = page.messages.filter { it.tracked && it.id !in page.new }
        confirmHeld(snapshot.revision, shown.map { it.id })
        for (message in shown) {
            val tag = messageNoticeTag(message.id)
            val notice = active[tag] ?: continue
            if (previous[tag]?.postTime != notice.postTime || (issued[tag] ?: 0) > snapshot.revision) continue
            val kind = notice.notification.channelId
            if (kind == REPLY || (kind == QUESTION && message.id !in page.owed)) {
                manager.cancel(tag, notice.id)
                if (replies.remove(tag)) reconcileGroupAfterQueue()
            }
        }
        updateGroup(replies.size)
    }

    private fun post(id: String, kind: String) {
        if (!manager.allows(kind)) return
        val route = Intent(Intent.ACTION_VIEW, Routes.url(Route.Message(id)), context, MainActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        val title = if (kind == REPLY) "jarvis replied" else "jarvis needs a reply"
        val tag = messageNoticeTag(id)
        val notice = notification(context, kind, title, route)
        if (kind == REPLY) {
            postingReplies.add(tag)
            notice.setGroup(ReplyGroup).setGroupAlertBehavior(NotificationCompat.GROUP_ALERT_SUMMARY)
                .setDeleteIntent(groupDismissed(tag))
        }
        issued[tag] = ++revision
        manager.notify(tag, 0, notice.build())
        if (kind == REPLY) reconcileGroupAfterQueue()
    }

    // Posting and cancelling are queued by Android. Recount once from the manager after the burst.
    private fun reconcileGroupAfterQueue() {
        groupHandler.removeCallbacks(reconcileGroup)
        groupHandler.postDelayed(reconcileGroup, 250)
    }

    private fun replyTags(): MutableSet<String> {
        val active = manager.activeNotifications.filter {
            it.notification.channelId == REPLY && it.notification.group == ReplyGroup && it.tag != ReplyGroup
        }.mapTo(mutableSetOf()) { it.tag }
        // Android can cancel children with their summary. Account for queued posts
        // until the manager acknowledges them as active.
        postingReplies.removeAll(active)
        return active
    }

    @Synchronized
    private fun settleGroup() {
        val active = replyTags()
        // A blocked or rate-limited post may never be acknowledged. Don't invent
        // a count or cancel an apparently empty group based on that uncertainty.
        updateGroup(active.size)
        postingReplies.clear()
    }

    @Synchronized
    fun dismissed(tag: String) {
        if (tag == ReplyGroup) postingReplies.clear() else postingReplies.remove(tag)
        updateGroup()
    }

    @Synchronized
    private fun updateGroup() = updateGroup(replyTags().size)

    private fun updateGroup(count: Int) {
        if (count == 0) {
            if (postingReplies.isEmpty()) manager.cancel(ReplyGroup, 0)
        } else if (manager.allows(REPLY)) {
            val summary = notification(context, REPLY, "jarvis · $count new", Intent(context, MainActivity::class.java))
                .setGroup(ReplyGroup)
                .setGroupSummary(true)
                .setGroupAlertBehavior(NotificationCompat.GROUP_ALERT_SUMMARY)
                .setOnlyAlertOnce(true)
                .setDeleteIntent(groupDismissed(ReplyGroup))
                .setAutoCancel(false)
            manager.notify(ReplyGroup, 0, summary.build())
        }
    }

    private fun groupDismissed(tag: String): PendingIntent {
        val intent = Intent(context, NoticeDismissed::class.java).setData(
            Uri.Builder().scheme("jarvis-notice").authority("dismiss").appendPath(tag).build(),
        )
        return PendingIntent.getBroadcast(context, 0, intent, PendingIntent.FLAG_IMMUTABLE)
    }

    companion object {
        private const val ReplyGroup = "jarvis-replies"
        @Volatile private var instance: PhoneNotices? = null

        fun get(context: Context): PhoneNotices = instance ?: synchronized(this) {
            instance ?: PhoneNotices(context.applicationContext).also { instance = it }
        }
    }
}

private data class Slot(val generation: String, val id: String?, val addressHash: String?)

internal enum class SetupRepair { RETRY, SETTINGS, SIGN_IN }

internal data class PhoneSetup(val generation: String?, val movesAlerts: Boolean, val repair: SetupRepair?)

internal class PhoneAlerts private constructor(context: Context) {
    private val api = HomeApi(context)
    private val preferences = context.getSharedPreferences("phone-alerts", Context.MODE_PRIVATE)
    private val id by lazy {
        preferences.getString("installation", null) ?: UUID.randomUUID().toString().also {
            if (!preferences.edit().putString("installation", it).commit()) {
                throw IOException("could not save phone installation")
            }
        }
    }
    private val appContext = context.applicationContext
    private val manager = context.getSystemService(NotificationManager::class.java)
    private val callbackScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    // Firebase registration waits for this callback. Publish its address before any slot I/O.
    private val addresses = Mutex()
    private val changes = Mutex()
    private val registered = MutableStateFlow(preferences.getString("registered", null))
    private val offer = MutableStateFlow<PhoneSetup?>(null)
    val setup = offer.asStateFlow()

    // Only a repair hint survives interruption. A new claim always needs a new tap.
    private var pendingRepair: String?
        get() = preferences.getString("setup", null)
        set(value) {
            if (!preferences.edit().putString("setup", value).commit()) throw IOException("could not save alert setup")
        }

    fun hasPermission(): Boolean = manager.areNotificationsEnabled()

    suspend fun begin(generation: String): Boolean = changes.withLock {
        if (offer.value?.generation != generation) return@withLock false
        try {
            pendingRepair = "retry"
            true
        } catch (_: IOException) {
            offer.value = offer.value?.copy(repair = SetupRepair.RETRY)
            false
        }
    }

    suspend fun denied() = changes.withLock {
        if (pendingRepair == null) return@withLock
        try {
            pendingRepair = "settings"
        } catch (_: IOException) {
            // The current visit can still open Android settings.
        }
        offer.value = PhoneSetup(offer.value?.generation, offer.value?.movesAlerts == true, SetupRepair.SETTINGS)
    }

    private suspend fun read(): Slot = withContext(Dispatchers.IO) {
        api.request(PHONE).use { it.slot() }
    }

    private fun okhttp3.Response.slot(): Slot {
        if (!isSuccessful) throw IOException("phone status unavailable")
        val json = json()
        val tag = header("ETag").orEmpty()
        if (tag.length != 38 || tag.first() != '"' || tag.last() != '"' ||
            !canonicalUuid(tag.substring(1, 37))) throw IOException("invalid phone generation")
        val owner = json.opt("installation_id")
        val address = json.opt("address_hash")
        if (owner === JSONObject.NULL && address === JSONObject.NULL) return Slot(tag, null, null)
        if (owner !is String || !canonicalUuid(owner) || address !is String ||
            !address.matches(Regex("[0-9a-f]{64}"))) throw IOException("invalid phone registration")
        return Slot(tag, owner, address)
    }

    private fun hash(fid: String): String = MessageDigest.getInstance("SHA-256")
        .digest(fid.toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }

    private suspend fun update(current: Slot, fid: String, replace: Boolean): Slot {
        val addressHash = hash(fid)
        if (current.id == id && current.addressHash == addressHash) return current
        val body = JSONObject().put("installation_id", id).put("fid", fid).put("replace", replace)
            .toString().toRequestBody("application/json".toMediaType())
        try {
            val result = withContext(Dispatchers.IO) {
                api.request(PHONE, "PUT", body, mapOf("If-Match" to current.generation))
                    .use { if (it.isSuccessful) it.slot() else null }
            }
            if (result != null && result.id == id && result.addressHash == addressHash) return result
        } catch (error: SignInRequired) {
            throw error
        } catch (_: IOException) {
            // The server may have committed the slot before contact was lost.
        }
        return read()
    }

    fun registered(fid: String) {
        callbackScope.launch {
            try {
                addresses.withLock {
                    if (FirebaseInstallations.getInstance().id.await() != fid) return@launch
                    if (!preferences.edit().putString("registered", fid).commit()) return@launch
                    registered.value = fid
                }
                changes.withLock {
                    if (registered.value != fid) return@withLock
                    val slot = read()
                    if (slot.id == id && registered.value == fid) present(update(slot, fid, replace = false), fid)
                }
            } catch (_: IOException) {
                // A foreground read will reconcile the confirmed SDK address after login.
            } catch (_: IllegalStateException) {
                // Firebase configuration is absent or unusable.
            }
        }
    }

    private fun present(slot: Slot, fid: String?) {
        if (slot.id == id && fid != null && slot.addressHash == hash(fid)) {
            if (pendingRepair != null) pendingRepair = null
            offer.value = null
        } else {
            val repair = when {
                pendingRepair == "settings" && !hasPermission() -> SetupRepair.SETTINGS
                pendingRepair != null || slot.id == id -> SetupRepair.RETRY
                else -> null
            }
            offer.value = PhoneSetup(slot.generation, slot.id != null && slot.id != id, repair)
        }
    }

    private fun failed(repair: SetupRepair) {
        offer.value = when {
            pendingRepair == null -> null
            pendingRepair == "settings" && !hasPermission() -> PhoneSetup(null, false, SetupRepair.SETTINGS)
            else -> PhoneSetup(null, false, repair)
        }
    }

    suspend fun refresh(home: Boolean) {
        if (!home && registered.value == null) return
        changes.withLock {
            try {
                val slot = read()
                val fid = registered.value
                if (slot.id == id && fid != null && FirebaseInstallations.getInstance().id.await() == fid) {
                    present(update(slot, fid, replace = false), fid)
                } else {
                    present(slot, null)
                }
            } catch (_: SignInRequired) {
                failed(SetupRepair.SIGN_IN)
            } catch (_: IOException) {
                failed(SetupRepair.RETRY)
            } catch (_: IllegalStateException) {
                failed(SetupRepair.RETRY)
            }
        }
    }

    private suspend fun registerAddress(): String {
        if (FirebaseApp.getApps(appContext).isEmpty()) throw IOException("push setup required")
        val messaging = FirebaseMessaging.getInstance()
        return withTimeoutOrNull(15_000) {
            runInterruptible(Dispatchers.IO) { messaging.isAutoInitEnabled = true }
            messaging.register().await()
            val latest = FirebaseInstallations.getInstance().id.await()
            registered.filterNotNull().first { it == latest }
        } ?: throw IOException("phone address unconfirmed")
    }

    suspend fun connect(generation: String) {
        try {
            manager.prepareChannels()
            val fid = registerAddress()
            changes.withLock {
                if (FirebaseInstallations.getInstance().id.await() != fid) throw IOException("phone address changed")
                val slot = read()
                if (registered.value != fid) throw IOException("phone address changed")
                val observed = if (slot.generation == generation) update(slot, fid, replace = true) else slot
                present(observed, fid)
            }
        } catch (_: SignInRequired) {
            changes.withLock { failed(SetupRepair.SIGN_IN) }
        } catch (_: IOException) {
            changes.withLock { failed(SetupRepair.RETRY) }
        } catch (_: IllegalStateException) {
            changes.withLock { failed(SetupRepair.RETRY) }
        }
    }

    companion object {
        @Volatile private var instance: PhoneAlerts? = null

        fun get(context: Context): PhoneAlerts = instance ?: synchronized(this) {
            instance ?: PhoneAlerts(context.applicationContext).also { instance = it }
        }
    }
}

private suspend fun <T> Task<T>.await(): T = suspendCancellableCoroutine { continuation ->
    addOnCompleteListener { task ->
        if (task.isSuccessful) continuation.resume(task.result)
        else continuation.resumeWithException(IOException("push registration unavailable"))
    }
}

@Composable
internal fun PhoneSetupAction(phone: PhoneAlerts, signIn: () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val setup by phone.setup.collectAsState()
    var changing by remember { mutableStateOf(false) }
    var permissionGeneration by remember { mutableStateOf<String?>(null) }

    fun perform(operation: suspend () -> Unit) {
        changing = true
        scope.launch {
            try {
                operation()
            } finally {
                changing = false
            }
        }
    }

    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        val generation = permissionGeneration
        permissionGeneration = null
        if (generation != null) {
            perform { if (granted) phone.connect(generation) else phone.denied() }
        }
    }
    val action = setup ?: return
    Column(Modifier.padding(horizontal = 12.dp)) {
        if (action.movesAlerts) Text("enabling here moves future alerts to this phone.")
        val label = when (action.repair) {
            SetupRepair.SETTINGS -> "open notification settings"
            SetupRepair.SIGN_IN -> "sign in to finish alert setup"
            SetupRepair.RETRY -> "retry alert setup"
            null -> "enable alerts on this phone"
        }
        if (action.repair == SetupRepair.SETTINGS) Text("notifications are blocked on this phone.")
        if (action.repair == SetupRepair.RETRY) Text("alert setup is unconfirmed.")
        TextButton(enabled = !changing && permissionGeneration == null, onClick = {
            when {
                action.repair == SetupRepair.SIGN_IN -> signIn()
                action.repair == SetupRepair.SETTINGS && !phone.hasPermission() ->
                    context.startActivity(Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS)
                        .putExtra(Settings.EXTRA_APP_PACKAGE, context.packageName))
                action.generation == null -> perform { phone.refresh(true) }
                else -> perform {
                    if (!phone.begin(action.generation)) return@perform
                    if (phone.hasPermission()) phone.connect(action.generation)
                    else {
                        permissionGeneration = action.generation
                        permission.launch(Manifest.permission.POST_NOTIFICATIONS)
                    }
                }
            }
        }) { Text(label) }
    }
}
