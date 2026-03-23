"""
Basilisk XRC — Candid types and service definition for the IC Exchange Rate Canister.

Provides a typed Python interface for querying exchange rates from the
IC Exchange Rate Canister (XRC, ``uf6dk-hyaaa-aaaaq-qaaaq-cai``):

  - Asset, AssetClass — asset identification types
  - GetExchangeRateRequest — request parameters
  - ExchangeRate, ExchangeRateMetadata — response types
  - ExchangeRateError — error variants
  - XRCCanister — Service proxy for the XRC canister

Usage inside a canister::

    from basilisk.canisters.xrc import XRCCanister, xrc_canister
    from basilisk.canisters.xrc import Asset, AssetClass, GetExchangeRateRequest

    result = yield xrc_canister.get_exchange_rate(
        GetExchangeRateRequest(
            base_asset=Asset(symbol="BTC", class_={"Cryptocurrency": None}),
            quote_asset=Asset(symbol="USD", class_={"FiatCurrency": None}),
            timestamp=None,
        )
    ).with_cycles(1_000_000_000)
"""

from basilisk import (
    Opt,
    Principal,
    Record,
    Service,
    Variant,
    nat32,
    nat64,
    null,
    service_update,
    text,
)


# ---------------------------------------------------------------------------
# Asset identification
# ---------------------------------------------------------------------------

class AssetClass(Variant, total=False):
    """XRC asset class: Cryptocurrency or FiatCurrency."""
    Cryptocurrency: null
    FiatCurrency: null


class Asset(Record):
    """XRC asset: symbol string + asset class."""
    symbol: text
    class_: AssetClass


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------

class GetExchangeRateRequest(Record):
    """Parameters for a get_exchange_rate call."""
    base_asset: Asset
    quote_asset: Asset
    timestamp: Opt[nat64]


# ---------------------------------------------------------------------------
# Response — metadata
# ---------------------------------------------------------------------------

class ExchangeRateMetadata(Record):
    """Metadata about how the exchange rate was determined."""
    decimals: nat32
    base_asset_num_queried_sources: nat64
    base_asset_num_received_rates: nat64
    quote_asset_num_queried_sources: nat64
    quote_asset_num_received_rates: nat64
    standard_deviation: nat64
    forex_timestamp: Opt[nat64]


# ---------------------------------------------------------------------------
# Response — rate
# ---------------------------------------------------------------------------

class ExchangeRate(Record):
    """Successful exchange rate response."""
    base_asset: Asset
    quote_asset: Asset
    timestamp: nat64
    rate: nat64
    metadata: ExchangeRateMetadata


# ---------------------------------------------------------------------------
# Error variants
# ---------------------------------------------------------------------------

class OtherError(Record):
    """Details for the ExchangeRateError.Other variant."""
    code: nat32
    description: text


class ExchangeRateError(Variant, total=False):
    """Error variants returned by get_exchange_rate."""
    AnonymousPrincipalNotAllowed: null
    Pending: null
    CryptoBaseAssetNotFound: null
    CryptoQuoteAssetNotFound: null
    StablecoinRateNotFound: null
    StablecoinRateTooFewRates: null
    StablecoinRateZeroRate: null
    ForexInvalidTimestamp: null
    ForexBaseAssetNotFound: null
    ForexQuoteAssetNotFound: null
    ForexAssetsNotFound: null
    RateLimited: null
    NotEnoughCycles: null
    FailedToAcceptCycles: null
    InconsistentRatesReceived: null
    Other: OtherError


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

class GetExchangeRateResult(Variant, total=False):
    """Result of a get_exchange_rate request."""
    Ok: ExchangeRate
    Err: ExchangeRateError


# ---------------------------------------------------------------------------
# Canister ID
# ---------------------------------------------------------------------------

XRC_CANISTER_ID = "uf6dk-hyaaa-aaaaq-qaaaq-cai"


# ---------------------------------------------------------------------------
# Service definition
# ---------------------------------------------------------------------------

class XRCCanister(Service):
    """
    Service proxy for the IC Exchange Rate Canister.

    Usage::

        from basilisk.canisters.xrc import xrc_canister, GetExchangeRateRequest, Asset
        result = yield xrc_canister.get_exchange_rate(
            GetExchangeRateRequest(
                base_asset=Asset(symbol="ICP", class_={"Cryptocurrency": None}),
                quote_asset=Asset(symbol="USD", class_={"FiatCurrency": None}),
                timestamp=None,
            )
        ).with_cycles(1_000_000_000)
    """

    @service_update
    def get_exchange_rate(
        self, args: GetExchangeRateRequest
    ) -> GetExchangeRateResult: ...


# ---------------------------------------------------------------------------
# Candid type strings for typed encoding/decoding
# ---------------------------------------------------------------------------

_ASSET_CLASS_CANDID = 'variant { Cryptocurrency : null; FiatCurrency : null }'
_ASSET_CANDID = f'record {{ symbol : text; class : {_ASSET_CLASS_CANDID} }}'

_METADATA_CANDID = (
    'record { decimals : nat32; '
    'base_asset_num_queried_sources : nat64; '
    'base_asset_num_received_rates : nat64; '
    'quote_asset_num_queried_sources : nat64; '
    'quote_asset_num_received_rates : nat64; '
    'standard_deviation : nat64; '
    'forex_timestamp : opt nat64 }'
)

_EXCHANGE_RATE_CANDID = (
    f'record {{ base_asset : {_ASSET_CANDID}; '
    f'quote_asset : {_ASSET_CANDID}; '
    f'timestamp : nat64; '
    f'rate : nat64; '
    f'metadata : {_METADATA_CANDID} }}'
)

_OTHER_ERROR_CANDID = 'record { code : nat32; description : text }'

_EXCHANGE_RATE_ERROR_CANDID = (
    'variant { '
    'AnonymousPrincipalNotAllowed : null; '
    'Pending : null; '
    'CryptoBaseAssetNotFound : null; '
    'CryptoQuoteAssetNotFound : null; '
    'StablecoinRateNotFound : null; '
    'StablecoinRateTooFewRates : null; '
    'StablecoinRateZeroRate : null; '
    'ForexInvalidTimestamp : null; '
    'ForexBaseAssetNotFound : null; '
    'ForexQuoteAssetNotFound : null; '
    'ForexAssetsNotFound : null; '
    'RateLimited : null; '
    'NotEnoughCycles : null; '
    'FailedToAcceptCycles : null; '
    'InconsistentRatesReceived : null; '
    f'Other : {_OTHER_ERROR_CANDID} }}'
)

_GET_EXCHANGE_RATE_RESULT_CANDID = (
    f'variant {{ Ok : {_EXCHANGE_RATE_CANDID}; '
    f'Err : {_EXCHANGE_RATE_ERROR_CANDID} }}'
)

XRCCanister._arg_types = {
    'get_exchange_rate': (
        f'record {{ base_asset : {_ASSET_CANDID}; '
        f'quote_asset : {_ASSET_CANDID}; '
        f'timestamp : opt nat64 }}'
    ),
}

XRCCanister._return_types = {
    'get_exchange_rate': _GET_EXCHANGE_RATE_RESULT_CANDID,
}


# ---------------------------------------------------------------------------
# Default canister instance
# ---------------------------------------------------------------------------

xrc_canister = XRCCanister(Principal.from_str(XRC_CANISTER_ID))
