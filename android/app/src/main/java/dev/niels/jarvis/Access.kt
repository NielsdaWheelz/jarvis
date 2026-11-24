package dev.niels.jarvis

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.AtomicFile
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import net.openid.appauth.AppAuthConfiguration
import net.openid.appauth.AuthorizationRequest
import net.openid.appauth.AuthorizationResponse
import net.openid.appauth.AuthorizationService
import net.openid.appauth.AuthorizationServiceConfiguration
import net.openid.appauth.GrantTypeValues
import net.openid.appauth.ResponseTypeValues
import net.openid.appauth.TokenRequest
import net.openid.appauth.TokenResponse
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONException
import org.json.JSONObject
import java.io.FileNotFoundException
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.security.GeneralSecurityException
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlin.coroutines.suspendCoroutine

internal class Access private constructor(private val context: Context) {
    private val lock = Mutex()
    private val transport = OkHttpClient.Builder().followRedirects(false).build()
    private val credential = AtomicFile(context.noBackupFilesDir.resolve("access"))
    private val changes = MutableStateFlow(0)
    val revision = changes.asStateFlow()
    private var loaded = false
    private var session: Session? = null

    fun signIn(activity: Activity) {
        activity.startActivity(Intent(activity, AccessLoginActivity::class.java))
    }

    suspend fun currentBearer(): String? = lock.withLock {
        if (!loaded) {
            session = withContext(Dispatchers.IO) { readSession() }
            loaded = true
        }
        val current = session ?: return@withLock null
        if (current.expiresAt - System.currentTimeMillis() > 60_000) {
            return@withLock current.token
        }
        val request = TokenRequest.Builder(current.configuration, BuildConfig.JARVIS_OAUTH_CLIENT_ID)
            .setGrantType(GrantTypeValues.REFRESH_TOKEN)
            .setRefreshToken(current.refresh)
            .setAdditionalParameters(resourceArgument)
            .build()
        withContext(NonCancellable) {
            val refreshed = exchange(request)
            if (refreshed == null) {
                withContext(Dispatchers.IO) { credential.delete() }
                session = null
                changes.update { it + 1 }
                null
            } else {
                val next = refreshed.session(current.refresh)
                withContext(Dispatchers.IO) { writeSession(next) }
                session = next
                next.token
            }
        }
    }

    suspend fun rejectedBearer(bearer: String) {
        lock.withLock {
            session?.takeIf { it.token == bearer }?.let { session = it.copy(expiresAt = 0) }
        }
    }

    suspend fun authorizationRequest(): AuthorizationRequest {
        if (BuildConfig.JARVIS_OAUTH_CLIENT_ID.isEmpty()) throw IOException("access setup required")
        return withContext(Dispatchers.IO) {
            try {
                val target = discover("${Routes.origin}/.well-known/cloudflare-access-protected-resource")
                val metadata = discover("$issuer/.well-known/oauth-authorization-server")
                if (target.getString("resource") != Routes.origin ||
                    !target.supports("authorization_servers", issuer) ||
                    metadata.getString("issuer") != issuer ||
                    !metadata.supports("code_challenge_methods_supported", "S256") ||
                    !metadata.supports("response_types_supported", "code") ||
                    !metadata.supports("grant_types_supported", GrantTypeValues.AUTHORIZATION_CODE) ||
                    !metadata.supports("grant_types_supported", GrantTypeValues.REFRESH_TOKEN) ||
                    !metadata.supports("token_endpoint_auth_methods_supported", "none")
                ) throw IOException("access discovery did not match jarvis")
                val configuration = AuthorizationServiceConfiguration(
                    trustedEndpoint(metadata.getString("authorization_endpoint")),
                    trustedEndpoint(metadata.getString("token_endpoint")),
                )
                AuthorizationRequest.Builder(
                    configuration,
                    BuildConfig.JARVIS_OAUTH_CLIENT_ID,
                    ResponseTypeValues.CODE,
                    callback,
                )
                    .setNonce(null)
                    .setAdditionalParameters(resourceArgument)
                    .build()
                    .also {
                        if (it.codeVerifierChallengeMethod != "S256") throw IOException("secure sign-in is unavailable")
                    }
            } catch (_: JSONException) {
                throw IOException("access discovery is invalid")
            }
        }
    }

    suspend fun complete(response: AuthorizationResponse) {
        if (response.request.redirectUri != callback || response.request.additionalParameters != resourceArgument) {
            throw IOException("access returned an invalid grant")
        }
        lock.withLock {
            withContext(NonCancellable) {
                val accepted = exchange(response.createTokenExchangeRequest(resourceArgument))
                    ?: throw IOException("access did not grant this account")
                val next = accepted.session(null)
                withContext(Dispatchers.IO) { writeSession(next) }
                loaded = true
                session = next
                changes.update { it + 1 }
            }
        }
    }

    private fun JSONObject.supports(field: String, value: String): Boolean {
        val entries = getJSONArray(field)
        return (0 until entries.length()).any { entries.getString(it) == value }
    }

    private fun discover(url: String): JSONObject {
        val request = Request.Builder().url(url).header("Accept", "application/json").build()
        transport.newCall(request).execute().use { response ->
            if (!response.isSuccessful) throw IOException("jarvis access is unavailable")
            return JSONObject(response.body?.string() ?: throw IOException("empty access discovery"))
        }
    }

    private suspend fun exchange(request: TokenRequest): TokenResponse? =
        withContext(Dispatchers.Main.immediate) {
            val options = AppAuthConfiguration.Builder()
                .setBrowserMatcher { false }
                .setConnectionBuilder { uri ->
                    (URL(trustedEndpoint(uri.toString()).toString()).openConnection() as HttpURLConnection)
                        .apply {
                            instanceFollowRedirects = false
                            connectTimeout = 15_000
                            readTimeout = 15_000
                        }
                }
                .build()
            val service = AuthorizationService(context, options)
            try {
                suspendCoroutine { continuation ->
                    service.performTokenRequest(request) { response, error ->
                        when {
                            response != null -> continuation.resume(response)
                            error?.error == "invalid_grant" -> continuation.resume(null)
                            else -> continuation.resumeWithException(IOException("jarvis access is unavailable"))
                        }
                    }
                }
            } finally {
                service.dispose()
            }
        }

    private fun TokenResponse.session(previousRefresh: String?): Session {
        val bearer = accessToken
        val expires = accessTokenExpirationTime
        val renewal = refreshToken ?: previousRefresh
        if (!tokenType.equals("Bearer", ignoreCase = true) || bearer.isNullOrEmpty() ||
            expires == null || renewal.isNullOrEmpty()
        ) throw IOException("access returned an incomplete grant")
        return Session(bearer, expires, renewal, request.configuration)
    }

    private fun readSession(): Session? {
        val bytes = try {
            credential.readFully()
        } catch (error: FileNotFoundException) {
            if (credential.baseFile.exists()) throw error
            return null
        }
        try {
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(
                Cipher.DECRYPT_MODE,
                key(),
                GCMParameterSpec(128, bytes, 0, 12),
            )
            val data = JSONObject(String(cipher.doFinal(bytes, 12, bytes.size - 12), Charsets.UTF_8))
            return Session(
                data.getString("token"),
                data.getLong("expires_at"),
                data.getString("refresh"),
                AuthorizationServiceConfiguration(
                    trustedEndpoint(data.getString("authorization_endpoint")),
                    trustedEndpoint(data.getString("token_endpoint")),
                ),
            )
        } catch (error: Exception) {
            if (error !is GeneralSecurityException && error !is IllegalArgumentException && error !is JSONException) {
                throw error
            }
            credential.delete()
            return null
        }
    }

    private fun writeSession(next: Session) {
        val data = JSONObject()
            .put("token", next.token)
            .put("expires_at", next.expiresAt)
            .put("refresh", next.refresh)
            .put("authorization_endpoint", next.configuration.authorizationEndpoint.toString())
            .put("token_endpoint", next.configuration.tokenEndpoint.toString())
        val bytes = try {
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.ENCRYPT_MODE, key())
            cipher.iv + cipher.doFinal(data.toString().toByteArray(Charsets.UTF_8))
        } catch (_: GeneralSecurityException) {
            throw IOException("this phone could not save access securely")
        }
        val output = credential.startWrite()
        try {
            output.write(bytes)
            credential.finishWrite(output)
        } catch (error: IOException) {
            credential.failWrite(output)
            throw error
        }
    }

    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        val alias = "jarvis-access"
        return store.getKey(alias, null) as SecretKey? ?: KeyGenerator
            .getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
            .apply {
                init(
                    KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                        .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                        .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                        .setKeySize(256)
                        .build(),
                )
            }
            .generateKey()
    }

    private data class Session(
        val token: String,
        val expiresAt: Long,
        val refresh: String,
        val configuration: AuthorizationServiceConfiguration,
    )

    companion object {
        val callback: Uri = Uri.parse("${Routes.origin}/auth/android")
        private const val issuer = "https://hidden-thunder-6080.cloudflareaccess.com"
        private val resourceArgument = mapOf("resource" to Routes.origin)
        private val authority = Uri.parse(issuer).encodedAuthority
        private var instance: Access? = null

        @Synchronized
        fun get(context: Context): Access =
            instance ?: Access(context.applicationContext).also { instance = it }

        private fun trustedEndpoint(raw: String): Uri {
            val uri = Uri.parse(raw)
            if (uri.scheme != "https" || uri.encodedAuthority != authority ||
                uri.encodedFragment != null || uri.encodedPath.isNullOrEmpty()
            ) throw IOException("access endpoint did not match jarvis")
            return uri
        }
    }
}
