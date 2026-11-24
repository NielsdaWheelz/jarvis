package dev.niels.jarvis

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.saveable.rememberSaveableStateHolder
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.lifecycle.compose.LifecycleResumeEffect
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    private val destination = MutableStateFlow<Uri?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (savedInstanceState == null) destination.value = intent.data
        setContent {
            val start = Routes.url(Route.Home).toString()
            var trail by rememberSaveable { mutableStateOf(arrayListOf(start)) }
            var alerts by rememberSaveable { mutableStateOf(false) }
            val holder = rememberSaveableStateHolder()
            val incoming by destination.collectAsState()
            val accessRevision by Access.get(this).revision.collectAsState()
            val scope = rememberCoroutineScope()
            val phone = remember { PhoneAlerts.get(this) }
            val warning by phone.warning.collectAsState()
            LifecycleResumeEffect(accessRevision) {
                val reconciliation = scope.launch { phone.reconcile() }
                onPauseOrDispose { reconciliation.cancel() }
            }

            fun navigate(route: Route) {
                val target = Routes.url(route).toString()
                if (trail.last() != target) {
                    val current = Routes.parse(Uri.parse(trail.last()))
                    val resolved = current == Route.Home ||
                        (current is Route.Canvas && current.revision == null &&
                            route is Route.Canvas && route.slug == current.slug)
                    val previous = trail.indexOf(target)
                    trail = ArrayList(when {
                        previous >= 0 -> trail.take(previous + 1)
                        resolved -> trail.dropLast(1) + target
                        else -> trail + target
                    })
                }
                alerts = false
            }

            fun back() {
                if (alerts) alerts = false
                else if (trail.size > 1) trail = ArrayList(trail.dropLast(1))
            }

            LaunchedEffect(incoming) {
                incoming?.let { uri ->
                    Routes.parse(uri)?.let(::navigate)
                    destination.value = null
                }
            }
            BackHandler(enabled = alerts || trail.size > 1, onBack = ::back)
            Column(Modifier.fillMaxSize().systemBarsPadding()) {
                if (!alerts) {
                    warning?.let { text ->
                        JarvisPaper(Modifier.fillMaxWidth()) {
                            TextButton(
                                onClick = { alerts = true },
                                modifier = Modifier.fillMaxWidth()
                            ) { Text(text) }
                        }
                    }
                }
                Box(Modifier.weight(1f)) {
                    if (alerts) {
                        Alerts(onBack = ::back)
                    } else {
                        holder.SaveableStateProvider(trail.last()) {
                            JarvisHome(
                                route = Routes.parse(Uri.parse(trail.last())) ?: Route.Home,
                                onNavigate = ::navigate,
                                onBack = if (trail.size > 1) ::back else null,
                                onAlerts = { alerts = true }
                            )
                        }
                    }
                }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        destination.value = intent.data
    }
}
