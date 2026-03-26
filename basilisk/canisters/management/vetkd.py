from basilisk import blob, null, Opt, Principal, Record, Variant, Vec


class VetKDCurve(Variant):
    bls12_381_g2: null


class VetKDKeyId(Record):
    curve: VetKDCurve
    name: str


class VetKDPublicKeyArgs(Record):
    canister_id: Opt[Principal]
    context: blob
    key_id: VetKDKeyId


class VetKDPublicKeyResult(Record):
    public_key: blob


class VetKDDeriveKeyArgs(Record):
    input: blob
    context: blob
    key_id: VetKDKeyId
    transport_public_key: blob


class VetKDDeriveKeyResult(Record):
    encrypted_key: blob
