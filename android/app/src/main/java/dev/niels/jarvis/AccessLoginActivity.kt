package dev.niels.jarvis

import android.content.ActivityNotFoundException
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.launch
import net.openid.appauth.AuthorizationException
import net.openid.appauth.AuthorizationRequest
import net.openid.appauth.AuthorizationResponse
import net.openid.appauth.AuthorizationService
import java.io.IOException

internal class AccessLoginActivity : ComponentActivity() {
    private val attempt: AccessAttempt by viewModels()
    private val access by lazy { Access.get(this) }
    private val authorization = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        attempt.pendingBrowser = false
        val data = result.data
        val failure = data?.let(AuthorizationException::fromIntent)
        val response = data?.let(AuthorizationResponse::fromIntent)
        when {
            response != null -> attempt.complete(access, response)
            failure?.error == "access_denied" -> attempt.failed("this account could not open jarvis")
            failure != null && failure != AuthorizationException.GeneralErrors.USER_CANCELED_AUTH_FLOW ->
                attempt.failed("sign-in could not finish")
            else -> finish()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (!attempt.started) {
            attempt.pendingBrowser = savedInstanceState?.getBoolean("browser") == true
            if (!attempt.pendingBrowser) attempt.prepare(access)
        }
        setContent {
            val state by attempt.state.collectAsState()
            LaunchedEffect(state.request, state.finished) {
                if (state.finished) {
                    finish()
                } else {
                    state.request?.let { request ->
                        attempt.state.value = AccessAttempt.State(detail = "waiting for your browser…")
                        val service = AuthorizationService(this@AccessLoginActivity)
                        try {
                            attempt.pendingBrowser = true
                            authorization.launch(service.getAuthorizationRequestIntent(request))
                        } catch (_: ActivityNotFoundException) {
                            attempt.pendingBrowser = false
                            attempt.failed("a browser is required to sign in")
                        } finally {
                            service.dispose()
                        }
                    }
                }
            }
            JarvisPaper {
                Surface(Modifier.fillMaxSize()) {
                    Column(
                        Modifier.safeDrawingPadding().padding(24.dp),
                        verticalArrangement = Arrangement.Center,
                        horizontalAlignment = Alignment.CenterHorizontally,
                    ) {
                        Text(state.detail)
                        TextButton(onClick = ::finish) { Text("back") }
                    }
                }
            }
        }
    }

    override fun onSaveInstanceState(outState: Bundle) {
        outState.putBoolean("browser", attempt.pendingBrowser)
        super.onSaveInstanceState(outState)
    }
}

internal class AccessAttempt : ViewModel() {
    data class State(
        val detail: String = "connecting to jarvis…",
        val request: AuthorizationRequest? = null,
        val finished: Boolean = false,
    )

    val state = MutableStateFlow(State())
    var pendingBrowser = false
    var started = false
        private set

    fun prepare(access: Access) {
        started = true
        viewModelScope.launch {
            try {
                state.value = State(request = access.authorizationRequest())
            } catch (error: IOException) {
                failed(error.message ?: "jarvis access is unavailable")
            }
        }
    }

    fun complete(access: Access, response: AuthorizationResponse) {
        started = true
        state.value = State(detail = "finishing sign-in…")
        viewModelScope.launch {
            try {
                access.complete(response)
                state.value = State(finished = true)
            } catch (error: IOException) {
                failed(error.message ?: "jarvis access is unavailable")
            }
        }
    }

    fun failed(detail: String) {
        state.value = State(detail = detail)
    }
}
