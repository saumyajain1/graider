# Account and password recovery setup

Google registration, sign-in, and explicit linking use the Google client described in the README. Password accounts can edit their name, change their password, and disconnect Google from Profile. Disconnecting requires the current password; a Google-only account must establish a password through its mailbox first. These actions preserve the account's assignments and results.

## Password recovery on Render

Render's free service blocks outbound SMTP ports [25, 465, and 587](https://render.com/docs/free). Graider sends recovery email through [Brevo's HTTPS API](https://developers.brevo.com/reference/send-transac-email), so it does not need an SMTP connection.

1. Create a Brevo account using its Free plan and complete its account/transactional-email activation. The [free allowance](https://help.brevo.com/hc/en-us/articles/208580669-FAQs-What-are-the-limits-of-the-Free-plan) is currently 300 emails per day.
2. Add a sender named **Graider** with an email address you control and complete the verification email. Brevo explains [sender verification](https://help.brevo.com/hc/en-us/articles/208836149-Create-a-new-sender-From-name-and-From-email). A custom sender domain is preferable for delivery; Brevo may [replace a free-domain sender address](https://help.brevo.com/hc/en-us/articles/14925263522578-Comply-with-Gmail-Yahoo-and-Microsoft-s-requirements-for-email-senders) with its compliant address.
3. Create an **API key**, not an SMTP key, in Brevo's SMTP & API settings.
4. Add these environment variables in Render, then save and redeploy:

   | Variable                      | Value                                                 |
   | ----------------------------- | ----------------------------------------------------- |
   | `BREVO_API_KEY`               | The Brevo API key                                     |
   | `GRAIDER_FROM_EMAIL`          | `Graider <your-verified-sender@example.com>`          |
   | `GRAIDER_PASSWORD_RESET_RATE` | Optional; defaults to `5/hour` per client IP          |
   | `GRAIDER_ACCOUNT_RATE`        | Optional; defaults to `10/min` for credential actions |

5. On the deployed sign-in page, choose **Forgot your password?**, request a link for your account, and check both your inbox and spam folder. Open the link, set/confirm a strong password, and sign in with it. Check Brevo's transactional logs if delivery fails.

The reset email uses `FRONTEND_URL` when set; otherwise it uses the app's allowed request origin. Keep `FRONTEND_URL` empty for the normal same-origin Render deployment. Reset links expire after one hour and cannot be reused after a password change. Their token is in the URL fragment, which is not sent to web-server logs or referrers. A generic request response avoids revealing whether an email is registered; it does not confirm delivery.

Keep the email API key in environment settings or ignored dotenv files. No subscription or recurring manual renewal is implemented in Graider; provider account activation and delivery policies apply. Without an email key, production recovery returns an unavailable message instead of pretending to send email.

## Local development

With `DJANGO_DEBUG=true` and no `BREVO_API_KEY`, emails print to the backend terminal. Request a reset link through the local app and copy the link from that terminal. For Docker, use `docker compose logs graider`. This tests the full recovery flow without sending mail externally. Treat printed reset links as credentials.

Name/password edits and Google disconnection are available from Profile. Password changes keep the session that made the change and invalidate other sessions; password recovery invalidates sessions and asks the user to sign in again.

## Admin sign-in

The `/admin/login/` page retains Django's password form and adds **Sign in with Google** when the server has Google credentials configured. It uses the existing Google client and callback, with the same CSRF protection, login rate limit, signed identity token, nonce and PKCE checks. After signing in, it returns to the requested admin page; external redirect destinations are ignored.

Only an active, existing staff account with Google already connected can use this admin flow. It does not register a new account, link accounts by matching email, or grant staff permissions. Connect Google from the regular profile first if you have a password account. With Google disabled, the page explains that it is unavailable on that server.
