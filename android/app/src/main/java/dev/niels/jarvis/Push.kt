package dev.niels.jarvis

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.lifecycle.compose.LifecycleResumeEffect
import com.google.android.gms.tasks.Task
import com.google.firebase.FirebaseApp
import com.google.firebase.installations.FirebaseInstallations
import com.google.firebase.messaging.FirebaseMessaging
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import java.io.IOException
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
private const val LINKED = "alerts linked to this phone"

private fun NotificationManager.prepareChannels() {
    createNotificationChannels(
        listOf(
            NotificationChannel(REPLY, "replies", NotificationManager.IMPORTANCE_DEFAULT),
            NotificationChannel(QUESTION, "questions", NotificationManager.IMPORTANCE_HIGH)
        )
    )
}

private fun NotificationManager.alertsAllowed(): Boolean =
    areNotificationsEnabled() && listOf(REPLY, QUESTION).all {
        getNotificationChannel(it)?.importance != NotificationManager.IMPORTANCE_NONE
    }

class Push : FirebaseMessagingService() {
    override fun onRegistered(installationId: String) {
        PhoneAlerts.get(this).registered(installationId)
    }

    override fun onMessageReceived(message: RemoteMessage) {
        val data = message.data
        if (data.keys != setOf("notice_id", "message_id", "kind")) return
        val notice = data["notice_id"] ?: return
        val reply = data["message_id"] ?: return
        val route = Route.Message(reply)
        if (runCatching { UUID.fromString(notice).toString() }.getOrNull() != notice ||
            Routes.parse(Routes.url(route)) != route
        ) return
        val kind = data["kind"] ?: return
        val title = when (kind) {
            REPLY -> "jarvis replied"
            QUESTION -> "jarvis needs a reply"
            else -> return
        }
        val manager = getSystemService(NotificationManager::class.java)
        if (!manager.areNotificationsEnabled()) return
        manager.prepareChannels()
        val destination = Intent(Intent.ACTION_VIEW, Routes.url(route), this, MainActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        val tap = PendingIntent.getActivity(this, 0, destination, PendingIntent.FLAG_IMMUTABLE)
        val notification = NotificationCompat.Builder(this, kind)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(title)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setAutoCancel(true)
            .setContentIntent(tap)
            .build()
        manager.notify(notice, 0, notification)
    }
}

private data class Slot(val generation: String, val id: String?, val addressHash: String?)

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
    private val changes = Mutex()
    private val registered = MutableStateFlow(preferences.getString("registered", null))
    private val attention = MutableStateFlow<String?>(null)
    val warning = attention.asStateFlow()

    fun report(status: String) {
        attention.value = status.takeIf { registered.value != null && it != LINKED }
    }

    private suspend fun read(): Slot = withContext(Dispatchers.IO) {
        api.request(PHONE).use { it.slot() }
    }

    private fun okhttp3.Response.slot(): Slot {
        if (!isSuccessful) throw IOException("phone status unavailable")
        val json = json()
        return Slot(
            header("ETag") ?: throw IOException("missing phone generation"),
            json.string("installation_id"),
            json.string("address_hash")
        )
    }

    private suspend fun update(current: Slot, fid: String, replace: Boolean): Slot {
        val addressHash = MessageDigest.getInstance("SHA-256")
            .digest(fid.toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }
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
        val observed = read()
        if (observed.id != id || observed.addressHash != addressHash) {
            throw IOException("phone change unconfirmed")
        }
        return observed
    }

    fun registered(fid: String) {
        callbackScope.launch {
            try {
                changes.withLock {
                    if (FirebaseInstallations.getInstance().id.await() != fid) return@withLock
                    if (!preferences.edit().putString("registered", fid).commit()) return@withLock
                    registered.value = fid
                    val slot = read()
                    if (slot.id == id) update(slot, fid, replace = false)
                }
            } catch (_: IOException) {
                // A foreground read will reconcile the confirmed SDK address after login.
            } catch (_: IllegalStateException) {
                // Firebase configuration is absent or unusable.
            }
        }
    }

    suspend fun reconcile() {
        if (registered.value == null) return
        report(try {
            status()
        } catch (_: SignInRequired) {
            "sign in to check alerts"
        } catch (_: IOException) {
            "phone status unconfirmed"
        } catch (_: IllegalStateException) {
            "push setup required"
        })
    }

    suspend fun status(): String = changes.withLock {
        val slot = read()
        if (slot.id == null) return@withLock "phone disconnected"
        if (slot.id != id) return@withLock "alerts linked to another phone"
        if (!manager.alertsAllowed()) {
            return@withLock "notifications are blocked on this phone"
        }
        val fid = registered.value ?: return@withLock "phone address unconfirmed"
        if (FirebaseInstallations.getInstance().id.await() != fid) {
            return@withLock "phone address unconfirmed"
        }
        update(slot, fid, replace = false)
        LINKED
    }

    suspend fun connect(): String {
        if (FirebaseApp.getApps(appContext).isEmpty()) return "push setup required"
        manager.prepareChannels()
        if (!manager.alertsAllowed()) return "notifications are blocked on this phone"
        val messaging = FirebaseMessaging.getInstance()
        val fid = withTimeoutOrNull(15_000) {
            // Firebase can synchronously wait for its installation ID here.
            runInterruptible(Dispatchers.IO) { messaging.isAutoInitEnabled = true }
            messaging.register().await()
            val latest = FirebaseInstallations.getInstance().id.await()
            registered.filterNotNull().first { it == latest }
        } ?: return "phone address unconfirmed"
        return changes.withLock {
            if (FirebaseInstallations.getInstance().id.await() != fid) {
                return@withLock "phone address changed · try again"
            }
            update(read(), fid, replace = true)
            LINKED
        }
    }

    suspend fun disconnect(): String = changes.withLock {
        val slot = read()
        if (slot.id != id) return@withLock "this phone is disconnected"
        try {
            val disconnected = withContext(Dispatchers.IO) {
                api.request(PHONE, "DELETE", headers = mapOf("If-Match" to slot.generation)).use {
                    it.isSuccessful && it.slot().id == null
                }
            }
            if (disconnected) return@withLock "phone disconnected"
        } catch (error: SignInRequired) {
            throw error
        } catch (_: IOException) {
            // Read current state before reporting an unconfirmed change.
        }
        if (read().id != id) "this phone is disconnected" else "phone change unconfirmed"
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
internal fun Alerts(onBack: () -> Unit) {
    val context = LocalContext.current
    val activity = context as MainActivity
    val phone = remember { PhoneAlerts.get(context) }
    val revision by Access.get(context).revision.collectAsState()
    val scope = rememberCoroutineScope()
    var state by remember { mutableStateOf("checking phone") }
    var changing by remember { mutableStateOf(false) }
    var signIn by remember { mutableStateOf(false) }
    var askingPermission by rememberSaveable { mutableStateOf(false) }

    fun perform(operation: suspend () -> String) {
        if (changing || askingPermission) return
        changing = true
        scope.launch {
            try {
                state = operation()
                signIn = false
            } catch (_: SignInRequired) {
                state = "sign in to set up alerts"
                signIn = true
            } catch (_: IOException) {
                state = "phone status unconfirmed"
            } catch (_: IllegalStateException) {
                state = "push setup required"
            } finally {
                phone.report(state)
                changing = false
            }
        }
    }

    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {
        askingPermission = false
        if (it) perform(phone::connect) else state = "notifications are blocked on this phone"
    }
    LaunchedEffect(revision) { perform(phone::status) }
    LifecycleResumeEffect(Unit) {
        perform(phone::status)
        onPauseOrDispose {}
    }
    JarvisPaper {
        Column(
            Modifier.fillMaxSize().systemBarsPadding().verticalScroll(rememberScrollState()).padding(24.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            OutlinedButton(onClick = onBack) { Text("back") }
            Text("phone alerts", style = MaterialTheme.typography.headlineLarge)
            Text(state)
            if (signIn) {
                Button(onClick = { Access.get(context).signIn(activity) }) { Text("sign in") }
            } else if (state == LINKED) {
                OutlinedButton(enabled = !changing, onClick = { perform(phone::disconnect) }) {
                    Text("disconnect this phone")
                }
            } else if (state == "notifications are blocked on this phone") {
                Button(onClick = {
                    context.startActivity(Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS)
                        .putExtra(Settings.EXTRA_APP_PACKAGE, context.packageName))
                }) { Text("open notification settings") }
            } else {
                Button(enabled = !changing, onClick = {
                    if (NotificationManagerCompat.from(context).areNotificationsEnabled()) {
                        perform(phone::connect)
                    } else {
                        askingPermission = true
                        permission.launch(Manifest.permission.POST_NOTIFICATIONS)
                    }
                }) { Text("enable alerts on this phone") }
            }
        }
    }
}
