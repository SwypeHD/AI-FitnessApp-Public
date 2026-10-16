package com.fittrack.app;

import android.app.Activity;
import android.content.Context;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.net.http.SslError;
import android.os.Build;
import android.os.Bundle;
import android.text.InputType;
import android.view.KeyEvent;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.SslErrorHandler;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;

/**
 * Thin native shell around the FitTrack web app running on the local network.
 *
 * A WebView has no secure-origin requirement, so this loads plain http:// from a LAN
 * host — something Chrome refuses to install as a standalone PWA.
 *
 * The server address is stored in SharedPreferences and editable in-app, so a DHCP
 * change doesn't require rebuilding the APK.
 */
public class MainActivity extends Activity {

    private static final String PREFS = "fittrack";
    private static final String KEY_URL = "server_url";
    private static final String DEFAULT_URL = "https://192.168.1.100:8443/static/index.html";

    private WebView web;
    private View setupView;
    private EditText urlInput;
    private TextView setupMessage;
    private FrameLayout root;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);

        root = new FrameLayout(this);
        root.setLayoutParams(new ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));

        web = new WebView(this);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);          // localStorage: theme + last page
        s.setDatabaseEnabled(true);
        s.setLoadWithOverviewMode(true);
        s.setUseWideViewPort(true);
        s.setSupportZoom(false);
        s.setBuiltInZoomControls(false);
        s.setMediaPlaybackRequiresUserGesture(false);
        // Always revalidate: the app shell changes whenever the server is updated.
        s.setCacheMode(WebSettings.LOAD_DEFAULT);

        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest req) {
                return false;   // keep all navigation inside the app
            }

            @Override
            public void onReceivedError(WebView v, WebResourceRequest req, WebResourceError err) {
                if (req != null && req.isForMainFrame()) {
                    showSetup("Couldn't reach the server. Check that it's running and that "
                            + "this phone is on the same network, then try again.");
                }
            }

            @Override
            public void onReceivedSslError(WebView v, SslErrorHandler handler, SslError err) {
                // Never proceed() — that would defeat the point of using TLS. The
                // bundled CA should make this unreachable; if it fires, the cert is
                // wrong or expired and the user needs to know.
                handler.cancel();
                showSetup("The server's security certificate isn't valid ("
                        + describeSslError(err)
                        + "). Regenerate it with scripts/make_certs.py and reinstall the "
                        + "app, or connect over http:// instead.");
            }

            @Override
            public void onPageFinished(WebView v, String url) {
                if (setupView != null && setupView.getVisibility() == View.VISIBLE
                        && !"about:blank".equals(url)) {
                    setupView.setVisibility(View.GONE);
                }
            }
        });

        root.addView(web, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));

        buildSetupView();
        root.addView(setupView, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        setupView.setVisibility(View.GONE);

        setContentView(root);

        if (state != null) {
            web.restoreState(state);
        } else {
            web.loadUrl(serverUrl());
        }
    }

    private static String describeSslError(SslError err) {
        if (err == null) return "unknown error";
        switch (err.getPrimaryError()) {
            case SslError.SSL_EXPIRED:    return "expired";
            case SslError.SSL_IDMISMATCH: return "wrong hostname/IP";
            case SslError.SSL_UNTRUSTED:  return "not signed by a trusted authority";
            case SslError.SSL_NOTYETVALID: return "not valid yet";
            case SslError.SSL_DATE_INVALID: return "bad validity dates";
            default:                      return "invalid";
        }
    }

    private SharedPreferences prefs() {
        return getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    private String serverUrl() {
        return prefs().getString(KEY_URL, DEFAULT_URL);
    }

    /** Native fallback screen: shown when the server can't be reached. */
    private void buildSetupView() {
        LinearLayout col = new LinearLayout(this);
        col.setOrientation(LinearLayout.VERTICAL);
        col.setBackgroundColor(Color.parseColor("#f5f5f4"));
        col.setPadding(48, 96, 48, 48);

        TextView title = new TextView(this);
        title.setText("FitTrack AI");
        title.setTextSize(22);
        title.setTextColor(Color.parseColor("#4338ca"));
        col.addView(title);

        setupMessage = new TextView(this);
        setupMessage.setTextSize(14);
        setupMessage.setTextColor(Color.parseColor("#57534e"));
        setupMessage.setPadding(0, 24, 0, 24);
        col.addView(setupMessage);

        TextView label = new TextView(this);
        label.setText("Server address");
        label.setTextSize(12);
        label.setTextColor(Color.parseColor("#78716c"));
        col.addView(label);

        urlInput = new EditText(this);
        urlInput.setInputType(InputType.TYPE_TEXT_VARIATION_URI);
        urlInput.setSingleLine(true);
        urlInput.setTextSize(15);
        col.addView(urlInput);

        Button retry = new Button(this);
        retry.setText("Connect");
        retry.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                String url = urlInput.getText().toString().trim();
                if (url.length() == 0) return;
                if (!url.startsWith("http://") && !url.startsWith("https://")) {
                    url = "http://" + url;
                }
                prefs().edit().putString(KEY_URL, url).apply();
                setupView.setVisibility(View.GONE);
                web.loadUrl(url);
            }
        });
        col.addView(retry);

        setupView = col;
    }

    private void showSetup(String message) {
        setupMessage.setText(message);
        urlInput.setText(serverUrl());
        setupView.setVisibility(View.VISIBLE);
    }

    @Override
    public boolean onKeyDown(int keyCode, KeyEvent event) {
        if (keyCode == KeyEvent.KEYCODE_BACK && setupView.getVisibility() != View.VISIBLE
                && web.canGoBack()) {
            web.goBack();
            return true;
        }
        return super.onKeyDown(keyCode, event);
    }

    @Override
    protected void onSaveInstanceState(Bundle out) {
        super.onSaveInstanceState(out);
        web.saveState(out);
    }
}
