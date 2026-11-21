import { clearUserCache, getCurrentUser, getToken } from "/static/js/auth.js";

async function readApiResponse(response) {
  const body = await response.text();
  let data = null;

  if (body) {
    try {
      data = JSON.parse(body);
    } catch {
      if (!response.ok) {
        const message = body.trim().slice(0, 160);
        throw new Error(
          `Request failed (${response.status})${message ? `: ${message}` : ""}`,
        );
      }
      throw new Error("The server returned an invalid response.");
    }
  }

  if (!response.ok) {
    throw new Error(
      data && typeof data.detail === "string"
        ? data.detail
        : `Request failed (${response.status}).`,
    );
  }

  if (!data || typeof data !== "object") {
    throw new Error("The server returned an empty response.");
  }

  return data;
}

function renderLikeButton(button, liked, likesCount) {
  button.classList.toggle("btn-danger", liked);
  button.classList.toggle("btn-outline-danger", !liked);
  button.setAttribute("aria-pressed", String(liked));
  button.querySelector("[data-like-label]").textContent = liked
    ? "Liked"
    : "Like";
  button.querySelector("[data-like-count]").textContent = String(likesCount);
}

function showStatus(button, message) {
  button.parentElement.querySelector("[data-like-status]").textContent = message;
}

function bindLikeButton(button, postId, state) {
  button.addEventListener("click", async () => {
    if (!state.authenticated) {
      window.location.href = "/login";
      return;
    }
    button.disabled = true;
    showStatus(button, "");

    try {
      const response = await fetch(`/api/posts/${postId}/like`, {
        method: state.liked ? "DELETE" : "PUT",
        headers: {
          Authorization: `Bearer ${getToken()}`,
        },
      });

      if (response.status === 401) {
        clearUserCache();
        localStorage.removeItem("access_token");
        window.location.href = "/login";
        return;
      }

      const data = await readApiResponse(response);
      state.liked = data.liked;
      renderLikeButton(button, state.liked, data.likes_count);
    } catch (error) {
      console.error("Error updating post like:", error);
      showStatus(button, error.message || "Could not update the like.");
    } finally {
      button.disabled = false;
    }
  });
}

async function initializeLikeButton(button) {
  if (button.dataset.likeInitialized) {
    return;
  }
  button.dataset.likeInitialized = "true";

  const postId = button.dataset.postId;
  const state = { authenticated: false, liked: false };
  const count = Number(button.querySelector("[data-like-count]").textContent);

  if (!getToken()) {
    renderLikeButton(button, false, count);
    state.authenticated = false;
    bindLikeButton(button, postId, state);
    button.disabled = false;
    return;
  }

  try {
    const user = await getCurrentUser();
    if (!user) {
      if (!getToken()) {
        renderLikeButton(button, false, count);
        bindLikeButton(button, postId, state);
        button.disabled = false;
        return;
      }
      throw new Error("Could not verify your session.");
    }

    const response = await fetch(`/api/posts/${postId}/like`, {
      headers: {
        Authorization: `Bearer ${getToken()}`,
      },
    });

    if (response.status === 401) {
      clearUserCache();
      localStorage.removeItem("access_token");
      renderLikeButton(button, false, count);
      showStatus(button, "Your session expired. Sign in to like posts.");
      bindLikeButton(button, postId, state);
      button.disabled = false;
      return;
    }

    const data = await readApiResponse(response);
    state.authenticated = true;
    state.liked = data.liked;
    renderLikeButton(button, state.liked, data.likes_count);
    bindLikeButton(button, postId, state);
    button.disabled = false;
  } catch (error) {
    console.error("Error loading post like:", error);
    showStatus(button, error.message || "Could not load the like status.");
  }
}

export function initializeLikeButtons(root) {
  for (const button of root.querySelectorAll("[data-like-button]")) {
    initializeLikeButton(button);
  }
}
