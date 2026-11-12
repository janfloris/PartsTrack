
document.addEventListener("DOMContentLoaded", () => {
    if (!("Notification" in window)) {
        return;
    }

    const enableButton = document.getElementById(
        "enable-notifications"
    );

    if (enableButton) {
        if (Notification.permission === "granted") {
            enableButton.textContent = "Desktop Notifications Enabled";
            enableButton.disabled = true;
        } else if (Notification.permission === "denied") {
            enableButton.textContent =
                "Notifications Blocked — Check Browser Settings";
            enableButton.disabled = true;
        } else {
            enableButton.addEventListener("click", async () => {
                const permission = await Notification.requestPermission();

                if (permission === "granted") {
                    enableButton.textContent =
                        "Desktop Notifications Enabled";
                    enableButton.disabled = true;
                }
            });
        }
    }

    // Prevent duplicate notification checks across open tabs.
    const shownNotifications = new Set();
    let initialized = false;
    let checking = false;

    async function checkNotifications() {
        if (checking) return;
        checking = true;

        try {
            const response = await fetch("/notifications/check", {
                cache: "no-store"
            });

            if (!response.ok) return;

            const data = await response.json();

            // Update the notification bell count.
            const badge = document.getElementById(
                "notification-count"
            );

            if (badge) {
                badge.textContent = data.unread_count;
                badge.style.display =
                    data.unread_count > 0 ? "" : "none";
            }

            // First check establishes existing notifications.
            // Don't display desktop alerts for old notifications.
            if (!initialized) {
                data.notifications.forEach(notification => {
                    shownNotifications.add(notification.id);
                });

                initialized = true;
                return;
            }

            for (const notification of data.notifications) {
                if (shownNotifications.has(notification.id)) {
                    continue;
                }

                shownNotifications.add(notification.id);

                if (Notification.permission !== "granted") {
                    continue;
                }

                const desktopNotification = new Notification(
                    "PartsTrack — All Parts Received",
                    {
                        body: notification.message,
                        tag: `partstrack-${notification.id}`
                    }
                );

                desktopNotification.onclick = () => {
                    window.focus();

                    window.location.href =
                        `/work-item/${notification.work_item_id}`;

                    desktopNotification.close();
                };
            }

        } catch (error) {
            console.error(
                "PartsTrack notification check failed:",
                error
            );
        } finally {
            checking = false;
        }
    }

    // Establish initial notification state.
    checkNotifications();

    // Check for new notifications every 15 seconds.
    setInterval(checkNotifications, 15000);
});
