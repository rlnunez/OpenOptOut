"""
gRPC HostService implementation.

Thin bridge: translates protobuf requests into CapabilityBroker calls and
catches permission errors, returning them as gRPC errors. All enforcement
lives in the broker; this file only marshals.
"""

import logging
from .broker import CapabilityError

log = logging.getLogger(__name__)


class HostServiceImpl:
    """Implements the generated HostServiceServicer via the capability broker."""

    def __init__(self, broker, pb):
        self.broker = broker
        self.pb = pb

    def _deny(self, context, msg):
        import grpc
        context.set_code(grpc.StatusCode.PERMISSION_DENIED)
        context.set_details(msg)

    # ---- storage ----

    def StorageGet(self, request, context):
        try:
            found, value = self.broker.storage_get(request.auth, request.key)
            return self.pb.StorageGetResponse(found=found, value=value)
        except CapabilityError as e:
            self._deny(context, str(e))
            return self.pb.StorageGetResponse(found=False, value="")

    def StorageSet(self, request, context):
        try:
            self.broker.storage_set(request.auth, request.key, request.value)
            return self.pb.StorageSetResponse(ok=True)
        except CapabilityError as e:
            self._deny(context, str(e))
            return self.pb.StorageSetResponse(ok=False, error=str(e))

    def StorageDelete(self, request, context):
        try:
            self.broker.storage_delete(request.auth, request.key)
            return self.pb.StorageDeleteResponse(ok=True)
        except CapabilityError as e:
            self._deny(context, str(e))
            return self.pb.StorageDeleteResponse(ok=False)

    def StorageList(self, request, context):
        try:
            keys = self.broker.storage_list(request.auth, request.prefix)
            return self.pb.StorageListResponse(keys=keys)
        except CapabilityError as e:
            self._deny(context, str(e))
            return self.pb.StorageListResponse(keys=[])

    # ---- settings ----

    def SettingGet(self, request, context):
        try:
            found, value = self.broker.setting_get(request.auth, request.key)
            return self.pb.SettingGetResponse(found=found, value=value)
        except CapabilityError as e:
            self._deny(context, str(e))
            return self.pb.SettingGetResponse(found=False, value="")

    def SettingSet(self, request, context):
        try:
            self.broker.setting_set(request.auth, request.key, request.value)
            return self.pb.SettingSetResponse(ok=True)
        except CapabilityError as e:
            self._deny(context, str(e))
            return self.pb.SettingSetResponse(ok=False, error=str(e))

    # ---- email-provider credentials ----

    def GetEmailCredentials(self, request, context):
        try:
            found, access_token, token_type, error = self.broker.email_credentials_get(
                request.auth, request.account_ref)
            return self.pb.GetEmailCredentialsResponse(
                found=found, access_token=access_token, token_type=token_type, error=error)
        except CapabilityError as e:
            self._deny(context, str(e))
            return self.pb.GetEmailCredentialsResponse(found=False, error=str(e))

    # ---- log ----

    def Log(self, request, context):
        try:
            self.broker.log_message(request.auth, request.level, request.message)
        except CapabilityError as e:
            self._deny(context, str(e))
        return self.pb.LogResponse(ok=True)

    # ---- events ----

    def EmitEvent(self, request, context):
        try:
            self.broker.emit_event(request.auth, request.event_type, dict(request.data))
            return self.pb.HostEventResponse(ok=True)
        except CapabilityError as e:
            self._deny(context, str(e))
            return self.pb.HostEventResponse(ok=False)

    # ---- broker read ----

    def BrokerGet(self, request, context):
        try:
            r = self.broker.broker_get(request.auth, request.broker_id)
        except CapabilityError as e:
            self._deny(context, str(e))
            return self.pb.BrokerGetResponse(found=False)
        if not r.get("found"):
            return self.pb.BrokerGetResponse(found=False)
        return self.pb.BrokerGetResponse(found=True, broker_id=r["broker_id"], name=r["name"],
                                         method=r["method"], difficulty=r["difficulty"], status=r["status"])

    def BrokerList(self, request, context):
        try:
            rows = self.broker.broker_list(request.auth, request.limit)
        except CapabilityError as e:
            self._deny(context, str(e))
            return self.pb.BrokerListResponse(brokers=[])
        return self.pb.BrokerListResponse(brokers=[
            self.pb.BrokerGetResponse(found=True, broker_id=r["broker_id"], name=r["name"],
                                      method=r["method"], difficulty=r["difficulty"], status=r["status"])
            for r in rows
        ])

    def BrokerHistory(self, request, context):
        try:
            r = self.broker.broker_history(request.auth, request.broker_id)
        except CapabilityError as e:
            self._deny(context, str(e))
            return self.pb.BrokerHistoryResponse(found=False)
        if not r.get("found"):
            return self.pb.BrokerHistoryResponse(found=False)
        return self.pb.BrokerHistoryResponse(
            found=True, total_requests=r["total_requests"], confirmed_count=r["confirmed_count"],
            failed_count=r["failed_count"], pending_count=r["pending_count"])

    # ---- request lifecycle ----

    def RequestGetStatus(self, request, context):
        try:
            r = self.broker.request_get_status(request.auth, request.request_id)
        except CapabilityError as e:
            self._deny(context, str(e))
            return self.pb.RequestGetStatusResponse(found=False)
        if not r.get("found"):
            return self.pb.RequestGetStatusResponse(found=False)
        return self.pb.RequestGetStatusResponse(
            found=True, request_id=r["request_id"], status=r["status"],
            method_used=r["method_used"], sent_at=r["sent_at"],
            confirmed_at=r["confirmed_at"], recheck_after=r["recheck_after"])

    def _mark_response(self, r):
        return self.pb.RequestMarkResponse(
            ok=r.get("ok", False), error=r.get("error", ""),
            previous_status=r.get("previous_status", ""), new_status=r.get("new_status", ""))

    def RequestMarkSent(self, request, context):
        try:
            r = self.broker.request_mark_sent(request.auth, request.request_id, request.reason)
        except CapabilityError as e:
            self._deny(context, str(e))
            return self.pb.RequestMarkResponse(ok=False, error=str(e))
        return self._mark_response(r)

    def RequestMarkConfirmed(self, request, context):
        try:
            r = self.broker.request_mark_confirmed(request.auth, request.request_id, request.reason)
        except CapabilityError as e:
            self._deny(context, str(e))
            return self.pb.RequestMarkResponse(ok=False, error=str(e))
        return self._mark_response(r)

    def RequestMarkFailed(self, request, context):
        try:
            r = self.broker.request_mark_failed(request.auth, request.request_id, request.reason)
        except CapabilityError as e:
            self._deny(context, str(e))
            return self.pb.RequestMarkResponse(ok=False, error=str(e))
        return self._mark_response(r)

    # ---- constrained opt-out email trigger ----

    def TriggerOptoutEmail(self, request, context):
        try:
            r = self.broker.trigger_optout_email(request.auth, request.request_id)
        except CapabilityError as e:
            self._deny(context, str(e))
            return self.pb.TriggerOptoutEmailResponse(ok=False, error=str(e))
        return self.pb.TriggerOptoutEmailResponse(ok=r.get("ok", False), error=r.get("error", ""))

    # ---- host-mediated HTTP fetch ----

    def HttpFetch(self, request, context):
        try:
            r = self.broker.http_fetch(request.auth, request.method, request.url,
                                       request.body, dict(request.headers))
        except CapabilityError as e:
            self._deny(context, str(e))
            return self.pb.HttpFetchResponse(ok=False, error=str(e))
        return self.pb.HttpFetchResponse(ok=r.get("ok", False), error=r.get("error", ""),
                                         status_code=r.get("status_code", 0), body=r.get("body", ""))

    # ---- custom recheck scheduling ----

    def ScheduleSetRecheck(self, request, context):
        try:
            r = self.broker.schedule_set_recheck(request.auth, request.request_id,
                                                 request.recheck_after_ts, request.reason)
        except CapabilityError as e:
            self._deny(context, str(e))
            return self.pb.ScheduleSetRecheckResponse(ok=False, error=str(e))
        return self.pb.ScheduleSetRecheckResponse(
            ok=r.get("ok", False), error=r.get("error", ""),
            previous_recheck=r.get("previous_recheck", 0), new_recheck=r.get("new_recheck", 0))
