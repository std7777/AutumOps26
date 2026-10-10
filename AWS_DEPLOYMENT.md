# AWS deployment for the course assignment

This guide uses the assignment's three tiers: a public Nginx web EC2, a private Python application EC2, and a private RDS MySQL database. The repository is prepared for both local SQLite and AWS MySQL. You do **not** need MySQL Server on your computer. No AWS resources are created by this repository.

The storefront records demonstration orders. It does not process payments, collect delivery addresses, or calculate delivery charges. Use test accounts until HTTPS is configured.

## 1. Prepare your AWS account and source

1. Choose one Region and use it for every resource. The examples below assume Amazon Linux 2023 on both EC2 instances; its login user is `ec2-user`.
2. Create an AWS Budget with an email alert. A budget is an alert, not a spending cap.
3. Commit and push this repository, including `static/images` and `static/fonts`, before cloning it on EC2. Do not upload `data/store.db`, `.git`, or a real `.env` file. A fresh RDS database will receive the eight sample products; local accounts and orders will not move automatically.
4. Decide on the RDS initial database name `morrow` and choose a private database password. Do not put the password in Git.

## 2. Build the network in the VPC console

Create a VPC with CIDR `10.0.0.0/16`, DNS resolution and DNS hostnames enabled. Create these subnets in that VPC:

| Subnet | CIDR | Availability Zone | Resource |
| --- | --- | --- | --- |
| Public web | `10.0.1.0/24` | A | Web EC2 |
| Private app | `10.0.2.0/24` | A | App EC2 |
| Private DB 1 | `10.0.3.0/24` | A | RDS subnet group |
| Private DB 2 | `10.0.4.0/24` | B | RDS subnet group |

`A` and `B` mean any two different Availability Zones in your chosen Region. RDS needs two subnets in different Availability Zones for a DB subnet group, even when you create a single DB instance. The assignment diagram only shows one DB subnet, so add the second one for AWS to accept the configuration. [RDS subnet requirements](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_CreateDBInstance.html)

Attach an Internet Gateway to the VPC. Create a **public** route table with `0.0.0.0/0` pointing to that gateway and associate only the public web subnet. Keep the app and DB subnets on a route table with only the VPC's local route. Do not assign public IP addresses to the app EC2 or RDS.

For initial package installation on the app EC2, you can temporarily create a NAT Gateway in the public subnet and a default route from the app subnet to the NAT Gateway. Remove that route and delete the NAT Gateway after installation. NAT Gateways incur hourly and data processing charges. [NAT pricing](https://docs.aws.amazon.com/vpc/latest/userguide/nat-gateway-pricing.html)

## 3. Create security groups

| Group | Inbound rule | Source |
| --- | --- | --- |
| `morrow-web` | TCP 80 | `0.0.0.0/0` |
| `morrow-web` | TCP 443, when HTTPS is ready | `0.0.0.0/0` |
| `morrow-web` | TCP 22 | Your current public IP `/32` only |
| `morrow-app` | TCP 8080 | `morrow-web` security group |
| `morrow-app` | TCP 22, for SSH through the web EC2 | `morrow-web` security group |
| `morrow-db` | TCP 3306 | `morrow-app` security group |

Leave the default outbound rules during setup. Do not open 8080 or 3306 to the internet. [RDS security group guidance](https://docs.aws.amazon.com/AmazonRDS/latest/gettingstartedguide/security-groups.html)

## 4. Launch EC2 and RDS

1. Launch two **Amazon Linux 2023** EC2 instances using the same SSH key pair. Place the web instance in `10.0.1.0/24`, enable a public IPv4 address, and attach `morrow-web`. Place the app instance in `10.0.2.0/24`, disable public IPv4, and attach `morrow-app`.
2. In RDS, create a **MySQL** DB subnet group using both private DB subnets. Create a MySQL DB instance in this VPC, select the subnet group, set **Public access: No**, attach `morrow-db`, and set **Initial database name: morrow**. Record its endpoint; use the endpoint hostname, not the changing private IP. [RDS creation guide](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_CreateDBInstance.html)
3. Record the web public IP and the app private IP. The app EC2 needs temporary outbound access for `dnf`, `git`, and `pip` if you use the commands below. Use the temporary NAT route from step 2 or transfer all packages through the web EC2.

## 5. Configure the private app EC2

Connect to the private app through the web instance. Put the following entries in your computer's OpenSSH config (`C:\Users\YOUR_NAME\.ssh\config` on Windows), replacing the placeholders. Keep the `.pem` file on your computer; do not copy it to the web EC2.

```sshconfig
Host morrow-web
    HostName WEB_PUBLIC_IP
    User ec2-user
    IdentityFile C:/path/to/key.pem

Host morrow-app
    HostName APP_PRIVATE_IP
    User ec2-user
    IdentityFile C:/path/to/key.pem
    ProxyJump morrow-web
```

Then run:

```powershell
ssh morrow-app
```

On the app EC2, while temporary outbound access is available:

```bash
sudo dnf install -y python3.11 git
git clone YOUR_REPOSITORY_URL storefront
cd ~/storefront
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements-aws.txt
```

Amazon Linux 2023's plain `python3` is Python 3.9; this app requires Python 3.10 or newer, so use `python3.11`. [Amazon Linux Python versions](https://docs.aws.amazon.com/linux/al2023/ug/python.html)

Create the private environment file from `deploy/morrow.env.example`:

```bash
sudo mkdir -p /etc/morrow
sudo cp deploy/morrow.env.example /etc/morrow/morrow.env
sudo chmod 600 /etc/morrow/morrow.env
sudo nano /etc/morrow/morrow.env
```

Enter the RDS **endpoint**, initial database name, database user/password, and your admin email/password. Use a new admin password of at least 12 characters. The app creates an admin account on its first start. The example file contains placeholders only. If you configure the RDS CA bundle, set `MORROW_DB_SSL_CA` to its path on this EC2.

Install and start the service:

```bash
sudo cp deploy/morrow.service /etc/systemd/system/morrow.service
sudo systemctl daemon-reload
sudo systemctl enable --now morrow
sudo systemctl status morrow
curl http://127.0.0.1:8080/api/products
```

The first start creates the MySQL tables and inserts the eight sample products only if the products table is empty. If startup fails, inspect `sudo journalctl -u morrow -n 100 --no-pager`. The service file assumes the code is at `/home/ec2-user/storefront`; edit it if you choose a different path.

## 6. Configure the public web EC2

Connect to the public web instance with SSH and install Nginx:

```bash
sudo dnf install -y nginx
```

Copy `deploy/morrow.nginx.conf` from the repository to the web EC2. Replace `APP_PRIVATE_IP` with the app EC2's private IP, then install the file in `/etc/nginx/conf.d/morrow.conf`. Check the active Nginx configuration and remove any competing default server block if necessary:

```bash
sudo nginx -t
sudo systemctl enable --now nginx
curl http://APP_PRIVATE_IP:8080/api/products
curl http://127.0.0.1/api/products
```

This Nginx configuration forwards the whole site, including images and `/api` requests, to the private app. It passes the original `Host` header so the app's same-origin check works. The public web EC2 is the only customer-facing server.

## 7. Verify and secure the demonstration

1. Open `http://WEB_PUBLIC_IP/` and verify the images and all eight items load.
2. Register a test customer, add an item to the cart, place an order, remove that order, and verify stock returns.
3. Log in with the admin credentials and edit a test item.
4. From the web EC2, `curl http://APP_PRIVATE_IP:8080/api/products` should work. From your own computer, direct access to `APP_PRIVATE_IP:8080` should fail. Direct connection from your computer to the RDS endpoint on 3306 should fail because it is private.
5. For a public site with real accounts, point a domain at the web EC2, configure HTTPS on Nginx, and then change `MORROW_HTTPS=1` in the app environment file and restart `morrow`. Until then, use test credentials only.
6. Once installation is complete, remove a temporary NAT Gateway and its app-subnet default route if you created one. The running app only needs private VPC access to RDS. Stop or delete AWS resources after the course demonstration to avoid continuing charges.
7. Before using the site commercially or publicly beyond a course demo, confirm permission to use each product photo and obtain an appropriate license for the Orange Avenue DEMO font or replace it.

The admin page accepts filenames for photos already present in `static/images`; it does not upload image files. Add any new image to the app EC2's `static/images` before entering its filename in the admin page.
