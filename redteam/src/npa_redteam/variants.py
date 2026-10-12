"""Bias-swap pair generator and synthetic persona registry (task 7.1).

IS/ISO/IEC TR 24027:2021: a fair system treats customers with the same story and the same
financials identically whatever their name, gender, religion, caste category or region. This
module builds those customers: :class:`NamePool` turns a :class:`~npa_redteam.cases.SwapSpec`
into variants, and :class:`PersonaRegistry` lets a target clone an account under a new
profile without touching its financials.
"""

from __future__ import annotations

import random
import zlib
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

from npa_contracts.enums import Lang
from npa_redteam.cases import BiasPairCase, SwapSpec, Variant

__all__ = [
    "NAME_POOL_PATH",
    "NamePool",
    "PersonaRegistry",
    "Profile",
    "ResolvedVariant",
    "default_name_pool",
    "resolve_variants",
]

NAME_POOL_PATH = Path(__file__).with_name("name_pools.yaml")


class Profile(BaseModel):
    """Name, protected attributes (contracts/data/protected_attributes.md) and city."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    gender: str
    religion: str
    caste_category: str
    state: str
    region: str
    city: str


@dataclass(frozen=True, slots=True)
class ResolvedVariant:
    label: str
    profile: Profile
    lang: Lang | None
    turns: tuple[str, ...] | None  # raw turn texts when the variant overrides the story
    turn_langs: tuple[Lang | None, ...] | None


class NamePool:
    def __init__(self, data: dict[str, object]) -> None:
        self._d = data

    @classmethod
    def load(cls, path: Path = NAME_POOL_PATH) -> NamePool:
        return cls(yaml.safe_load(path.read_text(encoding="utf-8")))

    def _get(self, *keys: str) -> object:
        node: object = self._d
        for key in keys:
            if not isinstance(node, dict) or key not in node:
                raise KeyError("name pool has no " + ".".join(keys))
            node = node[key]
        return node

    def _list(self, *keys: str) -> list[str]:
        node = self._get(*keys)
        if not isinstance(node, list) or not node:
            raise KeyError("name pool entry is not a non-empty list: " + ".".join(keys))
        return [str(v) for v in node]

    def values(self, axis: str) -> list[str]:
        return self._list("values", axis)

    def persona(self, customer_id: str) -> Profile:
        return Profile.model_validate(self._get("personas", customer_id))

    def _region(self, region: str) -> tuple[str, str]:
        spec = self._get("regions", region)
        assert isinstance(spec, dict)
        return str(spec["state"]), str(spec["city"])

    def _name(self, rng: random.Random, gender: str, religion: str, region: str) -> str:
        given = rng.choice(self._list("given_names", gender, religion))
        try:
            surnames = self._list("surname_overrides", gender, religion)
        except KeyError:
            surnames = self._list("surnames", region, religion)
        return f"{given} {rng.choice(surnames)}"

    def generate(self, base: Profile, spec: SwapSpec, case_id: str) -> list[Profile]:
        """``spec.count`` profiles: ``base`` first, then swaps that differ on every axis."""
        rng = random.Random(zlib.crc32(f"{spec.seed}:{case_id}".encode()))
        out = [base]
        seen = {base.model_dump_json()}
        for _ in range(spec.count * 20):
            if len(out) == spec.count:
                break
            attrs = base.model_dump()
            for axis in spec.axes:
                attrs[axis] = rng.choice([v for v in self.values(axis) if v != getattr(base, axis)])
            if "region" in spec.axes:
                attrs["state"], attrs["city"] = self._region(attrs["region"])
            if {"gender", "religion", "region"} & set(spec.axes):
                attrs["name"] = self._name(rng, attrs["gender"], attrs["religion"], attrs["region"])
            profile = Profile.model_validate(attrs)
            if profile.model_dump_json() not in seen:
                seen.add(profile.model_dump_json())
                out.append(profile)
        if len(out) < spec.count:
            raise ValueError(f"{case_id}: name pool cannot produce {spec.count} distinct variants")
        return out


@cache
def default_name_pool() -> NamePool:
    return NamePool.load()


def _label(base: Profile, profile: Profile, axes: tuple[str, ...]) -> str:
    if profile == base:
        return "base"
    return "/".join(str(getattr(profile, a)) for a in axes)


def resolve_variants(case: BiasPairCase, pool: NamePool | None = None) -> list[ResolvedVariant]:
    """The concrete variants of a bias case; the first one is the comparison baseline."""
    pool = pool or default_name_pool()
    base = pool.persona(case.persona)
    if case.swap is not None:
        axes = case.swap.axes
        return [
            ResolvedVariant(_label(base, p, axes), p, None, None, None)
            for p in pool.generate(base, case.swap, case.id)
        ]
    return [_explicit(base, v) for v in case.variants]


def _explicit(base: Profile, v: Variant) -> ResolvedVariant:
    overrides = {
        k: getattr(v, k)
        for k in ("name", "gender", "religion", "caste_category", "state", "region", "city")
        if getattr(v, k) is not None
    }
    turns = tuple(t.text for t in v.turns) if v.turns else None
    turn_langs = tuple(t.lang for t in v.turns) if v.turns else None
    return ResolvedVariant(v.label, base.model_copy(update=overrides), v.lang, turns, turn_langs)


class PersonaRegistry:
    """Synthetic test customers cloned from a base persona (same account data, new profile).

    Fakes and wrappers resolve a clone to its base for financial data and read the clone's
    profile for name and protected attributes.
    """

    def __init__(self) -> None:
        self._clones: dict[str, tuple[str, Profile]] = {}

    def clone(self, base_customer_id: str, profile: Profile) -> str:
        customer_id = f"CUST-RT-{len(self._clones) + 1:04d}"
        self._clones[customer_id] = (self.base_of(base_customer_id), profile)
        return customer_id

    def base_of(self, customer_id: str) -> str:
        return self._clones[customer_id][0] if customer_id in self._clones else customer_id

    def profile_of(self, customer_id: str) -> Profile | None:
        clone = self._clones.get(customer_id)
        return clone[1] if clone else None

    @staticmethod
    def account_of(customer_id: str) -> str:
        """``CUST-…`` → ``ACC-…`` (A7.0 ID convention, also for clones)."""
        return "ACC-" + customer_id.removeprefix("CUST-")

    def customer_of_account(self, account_id: str) -> str:
        return "CUST-" + account_id.removeprefix("ACC-")
