# pylint: disable=[invalid-name,import-outside-toplevel]
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, TypeAlias, Union  # noqa: UP035

from litestar import status_codes as status
from litestar.exceptions import HTTPException
from litestar.params import Parameter

from httpx_oauth.oauth2 import BaseOAuth2, GetAccessTokenError, OAuth2Error, OAuth2Token

if TYPE_CHECKING:
    import httpx
    from litestar import Request


AccessTokenState: TypeAlias = tuple[OAuth2Token, str | None]


class OAuth2AuthorizeCallbackError(OAuth2Error, HTTPException):
    """Error raised when an error occurs during the OAuth2 authorization callback.

    It inherits from [HTTPException][litestar.exceptions.HTTPException], so you can either keep
    the default Litestar error handling or implement something dedicated.

    !!! Note
        Due to the way the base `LitestarException` handles the `detail` argument,
        the `OAuth2Error` is ordered first here
    """

    def __init__(
        self,
        status_code: int,
        detail: Any = None,
        headers: Union[Dict[str, str], None] = None,  # noqa: UP007, UP006
        response: Union[httpx.Response, None] = None,  # noqa: UP007
        extra: Union[Dict[str, Any], List[Any]] | None = None,  # noqa: UP007, UP006
    ) -> None:
        super().__init__(message=detail)
        HTTPException.__init__(
            self, detail=detail, status_code=status_code, extra=extra, headers=headers
        )
        self.response = response


class OAuth2AuthorizeCallback:
    """Dependency callable to handle the authorization callback. It reads the query parameters and returns the access token and the state.

    Examples:
        ```py
        from litestar import get
        from httpx_oauth.integrations.litestar import OAuth2AuthorizeCallback
        from httpx_oauth.oauth2 import OAuth2

        client = OAuth2("CLIENT_ID", "CLIENT_SECRET", "AUTHORIZE_ENDPOINT", "ACCESS_TOKEN_ENDPOINT")
        oauth2_authorize_callback = OAuth2AuthorizeCallback(client, "oauth-callback")

        @get("/oauth-callback", name="oauth-callback", dependencies={"access_token_state": Provide(oauth2_authorize_callback)})
        async def oauth_callback(access_token_state: AccessTokenState)) -> Response:
            token, state = access_token_state
            # Do something useful
        ```
    """

    client: BaseOAuth2
    route_name: str | None
    redirect_url: str | None

    def __init__(
        self,
        client: BaseOAuth2,
        route_name: str | None = None,
        redirect_url: str | None = None,
    ) -> None:
        """Args:
        client: An [OAuth2][httpx_oauth.oauth2.BaseOAuth2] client.
        route_name: Name of the callback route, as defined in the `name` parameter of the route decorator.
        redirect_url: Full URL to the callback route.
        """
        assert (route_name is not None and redirect_url is None) or (
            route_name is None and redirect_url is not None
        ), "You should either set route_name or redirect_url"
        self.client = client
        self.route_name = route_name
        self.redirect_url = redirect_url

    async def __call__(
        self,
        request: Request,
        code: str | None = Parameter(query="code", required=False),
        code_verifier: str | None = Parameter(query="code_verifier", required=False),
        callback_state: str | None = Parameter(query="state", required=False),
        error: str | None = Parameter(query="error", required=False),
    ) -> AccessTokenState:
        if code is None or error is not None:
            raise OAuth2AuthorizeCallbackError(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error if error is not None else None,
            )

        if self.route_name:
            redirect_url = str(request.url_for(self.route_name))
        elif self.redirect_url:
            redirect_url = self.redirect_url

        try:
            access_token = await self.client.get_access_token(
                code,
                redirect_url,
                code_verifier,
            )
        except GetAccessTokenError as e:
            raise OAuth2AuthorizeCallbackError(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=e.message,
                response=e.response,
                extra={"message": e.message},
            ) from e

        return access_token, callback_state
