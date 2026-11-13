
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

    // Dismiss notifications without leaving the current page.
    document.addEventListener("submit", async (event) => {
        const form = event.target.closest(
            ".dismiss-notification-form"
        );

        if (!form) return;

        event.preventDefault();

        const button = form.querySelector("button[type='submit']");
        const notificationElement = form.closest(
            "[data-notification-id]"
        );

        if (button) button.disabled = true;

        try {
            const response = await fetch(form.action, {
                method: "POST",
                body: new FormData(form),
                headers: {
                    "X-Requested-With": "XMLHttpRequest"
                },
                credentials: "same-origin"
            });

            if (!response.ok) {
                throw new Error("Unable to dismiss notification");
            }

            const data = await response.json();

            // Remove the notification from the dropdown.
            if (notificationElement) {
                notificationElement.remove();
            }

            // Update the notification bell badge.
            const badge = document.getElementById(
                "notification-count"
            );

            if (badge) {
                badge.textContent = data.unread_count;
                badge.style.display =
                    data.unread_count > 0 ? "" : "none";
            }

            // Update the dropdown's "New" count.
            const dropdown = document.querySelector(
                '[aria-labelledby="notificationDropdown"]'
            );

            if (dropdown) {
                const newBadge = Array.from(
                    dropdown.querySelectorAll(".badge")
                ).find(element =>
                    element.textContent.trim().endsWith("New")
                );

                if (newBadge) {
                    newBadge.textContent =
                        `${data.unread_count} New`;

                    newBadge.style.display =
                        data.unread_count > 0 ? "" : "none";
                }

                // Display an empty message when all items are gone.
                if (!dropdown.querySelector("[data-notification-id]") &&
                    !dropdown.querySelector(".notification-empty-message")) {

                    const emptyMessage = document.createElement("div");
                    emptyMessage.className =
                        "notification-empty-message text-center text-muted py-4";
                    emptyMessage.textContent = "No notifications yet.";

                    const footer = dropdown.querySelector(".p-2.text-center");

                    if (footer) {
                        footer.before(emptyMessage);
                    }
                }
            }

        } catch (error) {
            console.error("Notification dismissal failed:", error);
            alert("Unable to dismiss notification. Please try again.");

            if (button) button.disabled = false;
        }
    });

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

    // Check for new notifications every 30 seconds.
    setInterval(checkNotifications, 30000);
});
