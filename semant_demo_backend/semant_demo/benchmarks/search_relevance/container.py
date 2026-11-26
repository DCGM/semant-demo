"""The benchmark store's own Weaviate container (``StoreSpec.host`` unset).

A container named ``StoreSpec.name`` with the named volume ``<name>-data``, both labelled
``org.semant.purpose=search-benchmark``, on loopback ports only (the spec's, or free ones chosen
when it is created). An existing container is reused (started if stopped) only when it carries
the label and runs the spec's image; a container or volume of that name without the label is
never touched. Nothing here deletes a container or a volume: recreating a store is
``docker rm -f <name> && docker volume rm <name>-data``.

The Docker CLI is used, as by ``scripts/local-dev.sh``; ownership of the data inside is checked
separately (the store's marker).
"""
from __future__ import annotations

import json
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass

import httpx

from semant_demo.benchmarks.search_relevance.store_api import StoreSpec

LABEL_KEY = "org.semant.purpose"
LABEL_VALUE = "search-benchmark"
LOOPBACK = "127.0.0.1"
READY_TIMEOUT = 120.0
DOCKER_TIMEOUT = 120.0


class ContainerError(RuntimeError):
    """Docker is missing, or a container or volume of the name is not the benchmark's."""


@dataclass(frozen=True)
class Endpoint:
    host: str
    rest_port: int
    grpc_port: int


def volume_name(spec: StoreSpec) -> str:
    return f"{spec.name}-data"


def free_port() -> int:
    """A loopback port nothing listens on now (the kernel's choice)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((LOOPBACK, 0))
        return s.getsockname()[1]


def run_arguments(spec: StoreSpec, rest_port: int, grpc_port: int) -> list[str]:
    """``docker run`` of a new store container: loopback ports, the labelled volume, no modules."""
    return [
        "docker", "run", "-d",
        "--name", spec.name,
        "--label", f"{LABEL_KEY}={LABEL_VALUE}",
        "--stop-timeout", "120",
        "-p", f"{LOOPBACK}:{rest_port}:8080",
        "-p", f"{LOOPBACK}:{grpc_port}:50051",
        "--mount", f"type=volume,source={volume_name(spec)},target=/var/lib/weaviate",
        "-e", "QUERY_DEFAULTS_LIMIT=25",
        "-e", "AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED=true",
        "-e", "PERSISTENCE_DATA_PATH=/var/lib/weaviate",
        "-e", "DEFAULT_VECTORIZER_MODULE=none",
        "-e", "CLUSTER_HOSTNAME=node1",
        "-e", "DISABLE_TELEMETRY=true",
        spec.weaviate_image, "--host", "0.0.0.0", "--port", "8080", "--scheme", "http",
    ]


def check_existing(spec: StoreSpec, inspected: dict) -> Endpoint:
    """The published endpoint of an existing container (``docker container inspect``); raises
    ``ContainerError`` when it is not the benchmark's or does not match the spec."""
    config = inspected.get("Config") or {}
    if (config.get("Labels") or {}).get(LABEL_KEY) != LABEL_VALUE:
        raise ContainerError(f"A container named {spec.name} exists without the label {LABEL_KEY}={LABEL_VALUE}; "
                             "not touching it. Choose another StoreSpec.name.")
    if config.get("Image") != spec.weaviate_image:
        raise ContainerError(f"Container {spec.name} runs {config.get('Image')}, not {spec.weaviate_image}. "
                             f"Recreate the store (docker rm -f {spec.name}; docker volume rm {volume_name(spec)}) "
                             "or use another StoreSpec.name.")
    bindings = (inspected.get("HostConfig") or {}).get("PortBindings") or {}
    rest, grpc = _bound_port(bindings, "8080/tcp"), _bound_port(bindings, "50051/tcp")
    if rest is None or grpc is None:
        raise ContainerError(f"Container {spec.name} does not publish both Weaviate ports.")
    for wanted, bound, what in ((spec.rest_port, rest, "REST"), (spec.grpc_port, grpc, "gRPC")):
        if wanted is not None and wanted != bound:
            raise ContainerError(f"Container {spec.name} publishes {what} on {bound}, not {wanted}.")
    return Endpoint(LOOPBACK, rest, grpc)


def _bound_port(bindings: dict, port: str) -> int | None:
    for binding in bindings.get(port) or ():
        if binding.get("HostIp") not in (LOOPBACK, "localhost"):
            raise ContainerError(f"Weaviate port {port} is published beyond loopback ({binding.get('HostIp')!r}).")
        if binding.get("HostPort"):
            return int(binding["HostPort"])
    return None


def _docker(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=DOCKER_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise ContainerError(f"docker {args[0]} did not answer within {DOCKER_TIMEOUT:.0f} s") from None
    if check and result.returncode != 0:
        raise ContainerError(f"docker {' '.join(args[:2])} failed: {result.stderr.strip()[-500:]}")
    return result


def _inspect(kind: str, name: str) -> dict | None:
    result = _docker(kind, "inspect", name, check=False)
    if result.returncode != 0:
        return None
    [found] = json.loads(result.stdout)
    return found


def ensure_container(spec: StoreSpec) -> Endpoint:
    """Start (or reuse) the store's container and wait until Weaviate is ready (blocking)."""
    if shutil.which("docker") is None:
        raise ContainerError("The Docker CLI is not installed; set StoreSpec.host to use a running instance.")
    _docker("info", "--format", "{{.ServerVersion}}")
    existing = _inspect("container", spec.name)
    if existing is not None:
        endpoint = check_existing(spec, existing)
        if not (existing.get("State") or {}).get("Running"):
            _docker("start", spec.name)
    else:
        volume = _inspect("volume", volume_name(spec))
        if volume is None:
            _docker("volume", "create", "--label", f"{LABEL_KEY}={LABEL_VALUE}", volume_name(spec))
        elif (volume.get("Labels") or {}).get(LABEL_KEY) != LABEL_VALUE:
            raise ContainerError(f"A volume named {volume_name(spec)} exists without the label "
                                 f"{LABEL_KEY}={LABEL_VALUE}; not using it.")
        rest = spec.rest_port or free_port()
        grpc = spec.grpc_port or free_port()
        while grpc == rest:
            grpc = free_port()
        result = subprocess.run(run_arguments(spec, rest, grpc), capture_output=True, text=True,
                                timeout=DOCKER_TIMEOUT)
        if result.returncode != 0:
            raise ContainerError(f"Could not start {spec.name}: {result.stderr.strip()[-500:]}")
        endpoint = Endpoint(LOOPBACK, rest, grpc)
    wait_ready(endpoint, spec.name)
    return endpoint


def wait_ready(endpoint: Endpoint, name: str, timeout: float = READY_TIMEOUT) -> None:
    url = f"http://{endpoint.host}:{endpoint.rest_port}/v1/.well-known/ready"
    deadline = time.monotonic() + timeout
    while True:
        try:
            if httpx.get(url, timeout=2.0).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        if time.monotonic() > deadline:
            raise ContainerError(f"Weaviate in {name} did not become ready within {timeout:.0f} s "
                                 f"(docker logs {name}).")
        time.sleep(0.5)
