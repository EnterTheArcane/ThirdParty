# pyright: basic, reportAttributeAccessIssue=false
import contextlib
from collections.abc import Generator
from ctypes import HRESULT, POINTER, c_ulong, c_wchar_p

import comtypes
from comtypes import BSTR, COMMETHOD, GUID, CoCreateInstance, IUnknown
from comtypes.automation import VARIANT_BOOL
from comtypes.safearray import _midlSAFEARRAY

from thirdparty._internal.util.setupconfiguration import VsSetupInstance
from thirdparty.errors import RecipeException


class ISetupInstance(IUnknown):
    _iid_ = GUID("{B41463C3-8866-43B5-BC33-2B0676F7F42E}")
    _methods_ = [
        COMMETHOD(
            [], HRESULT, "GetInstanceId",
            (["out", "retval"], POINTER(BSTR), "pbstrInstanceId")),
        COMMETHOD(
            [], HRESULT, "GetInstallDate",
            (["out", "retval"], POINTER(c_ulong * 2), "pInstallDate")),
        COMMETHOD(
            [], HRESULT, "GetInstallationName",
            (["out", "retval"], POINTER(BSTR), "pbstrInstallationName")),
        COMMETHOD(
            [], HRESULT, "GetInstallationPath",
            (["out", "retval"], POINTER(BSTR), "pbstrInstallationPath")),
        COMMETHOD(
            [], HRESULT, "GetInstallationVersion",
            (["out", "retval"], POINTER(BSTR), "pbstrInstallationVersion")),
        COMMETHOD(
            [], HRESULT, "GetDisplayName",
            (["in"], c_ulong, "lcid"),
            (["out", "retval"], POINTER(BSTR), "pbstrDisplayName")),
        COMMETHOD(
            [], HRESULT, "GetDescription",
            (["in"], c_ulong, "lcid"),
            (["out", "retval"], POINTER(BSTR), "pbstrDescription")),
        COMMETHOD(
            [], HRESULT, "ResolvePath",
            (["in"], c_wchar_p, "pwszRelativePath"),
            (["out", "retval"], POINTER(BSTR), "pbstrAbsolutePath")),
    ]


class ISetupPackageReference(IUnknown):
    _iid_ = GUID("{da8d8a16-b2b6-4487-a2f1-594ccccd6bf5}")
    _methods_ = [
        COMMETHOD(
            [], HRESULT, "GetId",
            (["out", "retval"], POINTER(BSTR), "pbstrId")),
    ]


class ISetupInstance2(ISetupInstance):
    _iid_ = GUID("{89143C9A-05AF-49B0-B717-72E218A2185C}")
    _methods_ = [
        COMMETHOD(
            [], HRESULT, "GetState",
            (["out", "retval"], POINTER(c_ulong), "pState")),
        COMMETHOD(
            [], HRESULT, "GetPackages",
            (["out", "retval"], POINTER(_midlSAFEARRAY(POINTER(ISetupPackageReference))), "ppsaPackages")),
        COMMETHOD(
            [], HRESULT, "GetProduct",
            (["out", "retval"], POINTER(POINTER(ISetupPackageReference)), "ppPackage")),
        COMMETHOD(
            [], HRESULT, "GetProductPath",
            (["out", "retval"], POINTER(BSTR), "pbstrProductPath")),
        COMMETHOD(
            [], HRESULT, "GetErrors",
            (["out", "retval"], POINTER(POINTER(IUnknown)), "ppErrorState")),
        COMMETHOD(
            [], HRESULT, "IsLaunchable",
            (["out", "retval"], POINTER(VARIANT_BOOL), "pfIsLaunchable")),
        COMMETHOD(
            [], HRESULT, "IsComplete",
            (["out", "retval"], POINTER(VARIANT_BOOL), "pfIsComplete")),
    ]


class ISetupInstanceCatalog(IUnknown):
    _iid_ = GUID("{9AD8E40F-39A2-40F1-BF64-0A6C50DD9EEB}")
    _methods_ = [
        COMMETHOD(
            [], HRESULT, "GetCatalogInfo",
            (["out", "retval"], POINTER(POINTER(IUnknown)), "ppCatalogInfo")),
        COMMETHOD(
            [], HRESULT, "IsPrerelease",
            (["out", "retval"], POINTER(VARIANT_BOOL), "pfIsPrerelease")),
    ]


class IEnumSetupInstances(IUnknown):
    _iid_ = GUID("{6380BCFF-41D3-4B2E-8B2E-BF8A6810C848}")
    _methods_ = [
        COMMETHOD(
            [], HRESULT, "Next",
            (["in"], c_ulong, "celt"),
            (["out"], POINTER(POINTER(ISetupInstance)), "rgelt"),
            (["out"], POINTER(c_ulong), "pceltFetched")),
    ]


class ISetupConfiguration(IUnknown):
    _iid_ = GUID("{42843719-DB4C-46C2-8E7C-64F1816EFD5B}")
    _methods_ = [
        COMMETHOD(
            [], HRESULT, "EnumInstances",
            (["out", "retval"], POINTER(POINTER(IEnumSetupInstances)), "ppEnumInstances")),
        COMMETHOD(
            [], HRESULT, "GetInstanceForCurrentProcess",
            (["out", "retval"], POINTER(POINTER(ISetupInstance)), "ppInstance")),
        COMMETHOD(
            [], HRESULT, "GetInstanceForPath",
            (["in"], c_wchar_p, "wzPath"),
            (["out", "retval"], POINTER(POINTER(ISetupInstance)), "ppInstance")),
    ]


class ISetupConfiguration2(ISetupConfiguration):
    _iid_ = GUID("{26AAB78C-4A60-49D6-AF3B-3C35BC93365D}")
    _methods_ = [
        COMMETHOD(
            [], HRESULT, "EnumAllInstances",
            (["out", "retval"], POINTER(POINTER(IEnumSetupInstances)), "ppEnumInstances")),
    ]


@contextlib.contextmanager
def _com_apartment() -> Generator[None]:
    try:
        comtypes.CoInitialize()
        entered = True
    except OSError:
        entered = False
    try:
        yield
    finally:
        if entered:
            comtypes.CoUninitialize()


def _read_instance(instance: ISetupInstance) -> VsSetupInstance:
    product_id: str | None = None
    package_ids: frozenset[str] = frozenset()
    is_complete = True
    is_prerelease = False

    instance2 = instance.QueryInterface(ISetupInstance2)
    with contextlib.suppress(comtypes.COMError):
        product = instance2.GetProduct()
        if product:
            product_id = product.GetId()
    with contextlib.suppress(comtypes.COMError):
        package_ids = frozenset(package.GetId() for package in instance2.GetPackages())
    with contextlib.suppress(comtypes.COMError):
        is_complete = bool(instance2.IsComplete())
    with contextlib.suppress(comtypes.COMError):
        catalog = instance.QueryInterface(ISetupInstanceCatalog)
        is_prerelease = bool(catalog.IsPrerelease())

    return VsSetupInstance(
        instance_id=instance.GetInstanceId(),
        installation_path=instance.GetInstallationPath(),
        installation_version=instance.GetInstallationVersion(),
        product_id=product_id,
        is_prerelease=is_prerelease,
        is_complete=is_complete,
        package_ids=package_ids,
    )


def enumerate_instances() -> list[VsSetupInstance]:
    with _com_apartment():
        try:
            config = CoCreateInstance(
                clsid=GUID("{177F0C4A-1CD3-4DE7-A32C-71DBBB9FA36D}"),
                interface=ISetupConfiguration2,
                clsctx=comtypes.CLSCTX_INPROC_SERVER)
        except (OSError, comtypes.COMError) as error:
            raise RecipeException("Visual Studio Setup Configuration COM API is not available. (no Visual Studio installer present).") from error

        enumerator = config.EnumAllInstances()
        instances: list[VsSetupInstance] = []
        while True:
            instance, fetched = enumerator.Next(1)
            if not fetched:
                break
            with contextlib.suppress(comtypes.COMError):
                # Skip a damaged/partial instance rather than aborting the scan.
                instances.append(_read_instance(instance))
        return instances
