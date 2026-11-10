# Server Setup from Scratch

This guide sets up the Engineering Resource Request system on a free Google Cloud server, starting from a new Google account. It ends with automatic deployment from GitHub, so every push to `main` updates the server.

Google's console screens change from time to time, so a button may be worded slightly differently from this guide, but the steps stay the same. For day-to-day operation after setup (logs, backups, restores, releases), see [部署指南.md](部署指南.md).

## Part 1: Create a Google account

1. Go to https://accounts.google.com/signup and create a new Google account, for example a dedicated Gmail address for the system. This account owns the Google Cloud project and sends the system's email.
2. Turn on **2-Step Verification** at https://myaccount.google.com/security. It is required later to create the app password the system uses for sending email.

## Part 2: Sign up for Google Cloud

1. Open https://console.cloud.google.com and sign in with the new account. Accept the terms of service.
2. Click **Start free** (or **Activate**). Choose your country and add a credit or debit card. The card is for identity verification. The free trial gives US$300 of credit for 90 days, and you are not charged unless you upgrade.
3. When the trial ends, Google asks you to **activate a full (pay-as-you-go) account** to keep your resources. Do this. The "Always Free" allowance used below continues, so one small server stays free.
4. Create a project: click the project selector at the top, then **New project**, and name it, for example, `erf`.
5. Set a spending alert so you are warned of any unexpected charge: **Billing → Budgets & alerts → Create budget**, set the amount to US$1 and keep the default email alerts.

## Part 3: Create the free virtual machine

1. Go to **Compute Engine → VM instances**. If asked, click **Enable** for the Compute Engine API and wait a minute.
2. Click **Create instance** and set:
   - **Name:** for example `erf-server`.
   - **Region:** `us-west1` (Oregon), `us-central1` (Iowa) or `us-east1` (South Carolina). Only these regions are covered by the free allowance.
   - **Machine configuration:** series **E2**, machine type **e2-micro**.
   - **Boot disk:** click **Change**, choose **Ubuntu**, the latest **LTS** version for **x86/64**. Set the disk type to **Standard persistent disk** and the size to **30 GB**.
   - **Firewall:** tick **Allow HTTP traffic** and **Allow HTTPS traffic**.
3. Click **Create**. The server starts within a minute.
4. Make the external IP address permanent so it does not change when the server restarts: **VPC network → IP addresses**, find the server's external address and click **Promote to static IP address** (or **Reserve**). Write the address down. Google charges a small fee for external IPv4 addresses in some cases, so check the **Billing** page after the first few days.

## Part 4: Give the server a domain name

1. Sign in at https://www.duckdns.org, for example with the same Google account.
2. Add a subdomain, for example `psbu`, enter the server's static IP address in the **current ip** field and click **update ip**.
3. The system's address will be `https://psbu.duckdns.org` (with your chosen name).

## Part 5: Prepare the server

Open **Compute Engine → VM instances** and click **SSH** next to the server. A terminal opens in your browser. Run each of the following commands in order.

Add 2 GB of swap space, which a 1 GB server needs as a safety margin:

```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
```

```bash
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

Install the Caddy web server, which provides HTTPS automatically:

```bash
sudo apt update && sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
```

```bash
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
```

```bash
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
```

```bash
sudo chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg /etc/apt/sources.list.d/caddy-stable.list
```

```bash
sudo apt update && sudo apt install -y caddy
```

Replace Caddy's default configuration with one that loads each site from its own file. The system's install script adds its site file there later:

```bash
sudo mkdir -p /etc/caddy/sites && echo 'import /etc/caddy/sites/*.caddy' | sudo tee /etc/caddy/Caddyfile && sudo systemctl reload caddy
```

If the server already hosts other sites through Caddy, do not replace the Caddyfile. Instead, add the line `import /etc/caddy/sites/*.caddy` at the end of the existing file and reload Caddy.

## Part 6: Connect automatic deployment from GitHub

These steps let GitHub install and update the system on the server whenever code is pushed to `main`.

1. **Create a deployment key.** In the SSH window, run:

   ```bash
   ssh-keygen -t ed25519 -N "" -C github-deploy -f ~/github-deploy
   ```

   ```bash
   cat ~/github-deploy.pub
   ```

   Copy the line that is printed. In the console, open the VM, click **Edit**, go to **SSH keys**, click **Add item**, paste the line and **Save**. Google creates the user `github-deploy` with administrator rights. If the project uses OS Login, keys added this way are ignored; in that case add the key to the user's `~/.ssh/authorized_keys` instead.

2. **Get the server's fingerprint**, which lets GitHub check that it is talking to your server. Replace the address with your static IP:

   ```bash
   echo "YOUR.STATIC.IP $(cut -d' ' -f1,2 /etc/ssh/ssh_host_ed25519_key.pub)"
   ```

3. **Create the Gmail app password** for sending email at https://myaccount.google.com/apppasswords. Name it `ERF` and copy the 16-character password. Google shows it only once.

4. **Add the settings in GitHub.** Open the repository's **Settings → Secrets and variables → Actions**.

   Under **Secrets**, add:

   | Name | Value |
   | --- | --- |
   | `DEPLOY_HOST` | The static IP address |
   | `DEPLOY_USER` | `github-deploy` |
   | `DEPLOY_SSH_KEY` | The full output of `cat ~/github-deploy` (the private key, including the BEGIN and END lines) |
   | `DEPLOY_KNOWN_HOSTS` | The line printed in step 2 |
   | `ERF_SMTP_PASSWORD` | The Gmail app password |

   Under **Variables**, add:

   | Name | Value |
   | --- | --- |
   | `DEPLOY_ENABLED` | `true` |
   | `ERF_DOMAIN` | Your domain, for example `psbu.duckdns.org` |
   | `ERF_SMTP_USERNAME` | The Gmail address |
   | `ERF_DEMO` | `true` to load demo data, or `false` for a clean start |

   Secret names must match exactly, in capital letters, and must be **repository** secrets on the **Actions** page. Secrets added under Environments, Dependabot or Codespaces are not visible to the deployment.

5. **Delete the key files from the server**, because the private key now lives only in GitHub:

   ```bash
   rm ~/github-deploy ~/github-deploy.pub
   ```

6. **Run the first deployment.** In GitHub, open **Actions → CI → Run workflow**, choose `main` and click **Run workflow**. It takes a few minutes. When all three jobs show green ticks, the system is installed. The deployment log shows `Email settings updated` when the email settings have reached the server.

## Part 7: Open the system and create your administrator

1. Open `https://psbu.duckdns.org` (your domain). If you deployed with demo data, the sign-in page lists the demo accounts, which all use the password `Demo@2026!`.
2. Create your own administrator account. In the server's SSH window, run the following with your own email and name:

   ```bash
   cd /opt/erf/current/backend && sudo -u erf bash -c 'set -a; . /etc/erf/erf.env; set +a; .venv/bin/erf create-admin --email you@company.com --name "Your Name"'
   ```

   The command prints a temporary password. Sign in with it, and the system asks you to choose your own password.
3. In **Settings**, add your users and set the team approvers in **Teams and approvers**. A team leader receives requests only after being added as an approver of their team.
4. Send yourself a test email from **Settings → Email delivery** to confirm that email works.

From then on, every push to `main` updates the server automatically, and the database is backed up before each update.

## Troubleshooting

| Symptom | Likely cause | What to do |
| --- | --- | --- |
| The deployment fails at "Install the release on the server" with a connection error | The SSH key, user or fingerprint is wrong, or port 22 is blocked | Check the four `DEPLOY_` secrets. In **VPC network → Firewall**, make sure a rule allows TCP port 22 from anywhere (the default `default-allow-ssh` rule does). |
| The deployment log says `ERF_SMTP_PASSWORD is empty` | The secret is missing, misnamed or in the wrong place | Add it as a repository secret on the Actions page, with the exact name, then run the workflow again. |
| The site does not open over HTTPS | The domain does not point to the server, or HTTP/HTTPS is not allowed | Check the IP address on DuckDNS, and that the VM allows HTTP and HTTPS traffic. Caddy needs both ports to obtain the certificate. |
| A test email shows `FAILED` with a 535 error | Gmail rejected the login | Create a new app password, update `ERF_SMTP_PASSWORD` and run the workflow again. |
