# ClawBack privacy policy

Last updated: 2026-10-28.

**This is a prototype policy for a hackathon demo.** ClawBack is a student hackathon project, not a company. This
page says plainly what the demo does with your data. It is not legal advice, and it will be reviewed before
ClawBack is offered to anyone outside the demo. The page at `/privacy` in the app shows the same text.

Before publishing, fill in the placeholder `[contact email]`.

## The short version

- ClawBack reads your email and bank transactions to find money you are losing or owed.
- Email access is read-only. If you allow drafts, ClawBack can also save a draft in your mailbox. It sends a gym
  cancellation email only when you click Send, and, if you turn it on, a monthly recap to your own address. It
  never cancels, pays or files anything.
- If you upload a Google Maps Timeline file, ClawBack keeps only the dates you visited a gym it knows. The file, its
  coordinates and every other place in it are discarded as it's read.
- You sign in to your email and your bank on their own pages. ClawBack never sees those passwords.
- ClawBack stores the facts it pulls out of your email, never the email text itself.
- The AI models run on Nebius Token Factory with Zero Data Retention on, so prompts are not kept.
- Nobody sells your data, shows you ads with it, or trains a model on it.
- You can disconnect a source or delete all your data at any time.

## Who runs the demo

The ClawBack team built the demo for the Nebius x NVIDIA Global AI Hackathon. The demo runs until judging ends in
December 2026. Questions and deletion requests go to `[contact email]`.

## Demo sessions

The demo has no accounts and no login. When you first open the dashboard, your browser gets a random session id. The
browser sends it with every request, and the server keeps your data under it. The id is kept in your browser's
storage on that device.

- The dashboard starts on a made-up demo month. Nothing in it is about a real person.
- Anyone who has your session id can see that session's data, so don't share it.
- Clearing your browser's site data starts a new session. The old session's data stays on the server until you use
  "Delete my data" or the demo closes.

## What ClawBack reads

### Email, through Nylas

ClawBack connects to Gmail, Outlook, Yahoo, iCloud and other inboxes through [Nylas](https://www.nylas.com), a
third-party email service. Nylas processes your mail on ClawBack's behalf.

- You sign in on your email provider's own page. Nylas keeps the provider's access tokens. ClawBack keeps only a
  Nylas grant id, which works only together with ClawBack's own Nylas key.
- For iCloud and some other IMAP inboxes, you type an app password on Nylas's page. ClawBack never sees it, but it
  gives Nylas full access to that mailbox.
- ClawBack reads up to 150 messages from the last 180 days that look like receipts, renewals, trials, price changes
  or travel notices. For each one it uses the sender, subject, date and text.
- **Drafts, if you allow them.** The sign-in page then also asks for permission to write drafts. ClawBack uses it only
  to save a draft you asked for, such as a cancellation email or a refund letter. For Gmail, Google's draft
  permission also allows sending mail. ClawBack uses it only for the gym email below.
- **Sending, only when you click Send.** For a gym that takes cancellation by email, ClawBack shows the finished
  email and sends it from your own inbox when you click Send and confirm. In the demo it goes to your own address,
  never to the gym. Connecting email just to send keeps the demo month and reads nothing from your inbox. Gmail asks
  for the send permission (gmail.send), which can only send, not read.

### Google Maps Timeline, if you upload it
- Google offers no way for apps to read location history, so you choose to upload the Timeline file from the
  Google Maps app. ClawBack reads it once, keeps only the dates of visits near a gym on its list (within about
  150 m), and discards the rest of the file: coordinates, other places, travel. Deleting your data deletes those
  dates too.

### The Gmail add-on, if you install it
- The add-on is a Chrome extension you load yourself. It reads one thing from your Gmail page: each sender's
  email address in the inbox list and in an open email. It compares the address with the services ClawBack flagged,
  inside your browser. No address, subject or email text is sent to ClawBack or anywhere else, and the add-on never
  changes or clicks anything in Gmail.
- It fetches the flags with a token that can only list them. Disconnecting it on the settings page, or deleting
  your data, revokes the token.

### Bank transactions, through Plaid

ClawBack reads bank and card transactions through [Plaid](https://plaid.com). The demo only connects Plaid's test
banks, with test logins.

- You sign in on Plaid's page. ClawBack never sees your bank username or password.
- ClawBack receives up to 180 days of transactions: the date, the description, the merchant name and the amount.
  It also gets the bank's name.

### A statement file, if you upload one

You can upload a bank statement as a CSV file instead. ClawBack reads the date, description and amount columns.

## What ClawBack does with it

Plain code does most of the work: it finds recurring charges, does every date and dollar calculation, and checks
each finding against a list of rules with official sources. Models only read text and write wording.

### AI models on Nebius Token Factory

ClawBack uses NVIDIA Nemotron models on [Nebius Token Factory](https://tokenfactory.nebius.com).

- Rules first set aside email that can't matter. Nemotron 3.5 Lightning reads the rest, a few thousand characters
  of each, and returns facts such as the merchant, a price or the days left in a trial.
- Nemotron 3 Super reads public plan and pricing pages. Nemotron 3 Ultra compares them with a summary of how you
  use a service, and writes cancellation emails from facts the code worked out.
- **Zero Data Retention is on** for ClawBack's Token Factory organization. Nebius does not store or log the prompts
  or the answers. Nebius does not use prompts to train models.

### Web search with Tavily

ClawBack uses [Tavily](https://www.tavily.com) to search the public web, for example to find a merchant's cancel
page or current plans. Tavily receives the search text only. That text is built from a merchant name, a bill type
(such as "internet") or, for a price check, a product and store name. Tavily never receives your name, your email
address, your account numbers or any email text.

## What ClawBack stores, and where

ClawBack keeps your session's data in one database on a server on Oracle Cloud Infrastructure, in its US East
(Ashburn, Virginia) region.

It stores:
- the facts pulled out of each email (kind, merchant, amounts, dates), with the sender, subject and date;
- your transactions (date, description, amount);
- the subscriptions, bills and findings worked out from them;
- your choices: check-in answers, "keep", "dismiss" and "done", and the amounts you say you got back;
- the connection details: the Nylas grant id, the Plaid access token, the account name and the last sync time;
- a log of each step (which model or service ran, how long it took, the tokens and the cost). It never holds email
  text, tokens or keys.

It does not store:
- **the text of your emails.** Email text stays in the server's memory while it is read, and is never written to
  disk or to logs;
- your email or bank passwords, which ClawBack never sees.

The Plaid access token and the Nylas grant id are **encrypted** in the database. The key that decrypts them stays on
the server, outside the database and outside the code.

The server also keeps request logs (time, address, path) for 14 days, to keep it running and secure. They don't
contain email text.

The front end runs on [Vercel](https://vercel.com), which sees standard request data such as your IP address and
the pages you load. It doesn't receive your email or bank data.

## What ClawBack never does

- It never sells your data or shares it for advertising.
- It never uses your data to train or improve an AI model, ours or anyone else's.
- No person reads your email or transactions, unless you ask us to look at a problem with your session, or it is
  needed for security or the law.
- It never cancels, pays, disputes or files anything. It sends one thing, a gym cancellation email, and only when you
  click Send. Everything else it prepares, and you make the final click.

## Google user data

ClawBack's use and transfer to any other app of information received from Google APIs will adhere to the
[Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy),
including the Limited Use requirements.

In practice, for Gmail data reached through Nylas:
- ClawBack uses it only to show you the subscriptions, bills and money owed that it finds, and to save drafts you ask
  for.
- It is shared only with the processors that provide those features (Nylas, and Nebius Token Factory for the
  models), never with anyone else.
- It is never used for ads, never sold, and never used to train AI models.
- People don't read it, except as described above.
- Email text is treated as untrusted and screened for hidden instructions before a model reads it.

## Your choices

- **Disconnect.** "Disconnect" removes the email or bank connection. ClawBack asks Nylas to delete the grant, or
  Plaid to remove the bank link, and drops that source's data.
- **Delete my data.** "Delete my data" removes everything ClawBack holds for your session, including the saved
  connections, and asks Nylas and Plaid to drop them.
- **Revoke access at the source.** You can also remove ClawBack's access in your Google, Microsoft or Yahoo account
  settings at any time.
- **When the demo closes**, after judging ends in December 2026, we delete the server and its database.

## Service providers

| Provider | What it does for ClawBack | What it receives |
|---|---|---|
| [Nylas](https://www.nylas.com/privacy-policy/) | Email sign-in, reading mail, saving drafts | Your mailbox access, as you grant it |
| [Plaid](https://plaid.com/legal/#end-user-privacy-policy) | Bank sign-in and transactions | What you share on Plaid's page |
| [Nebius Token Factory](https://docs.tokenfactory.nebius.com/legal/privacy-policy) | The AI models | Email text for the models, with Zero Data Retention |
| [Oracle Cloud Infrastructure](https://www.oracle.com/legal/privacy/) | The server and its database | The database, on its disk |
| [Tavily](https://www.tavily.com/privacy) | Web search | Merchant, bill type and product names in search text |
| [Vercel](https://vercel.com/legal/privacy-policy) | Hosts the web pages | Standard request data |

## Children

ClawBack is not meant for anyone under 18.

## Changes

If this policy changes, the date at the top changes too.

## Contact

Email `[contact email]` with questions or to ask us to delete a session's data.
