import importlib as _il
_m = _il.import_module('app.modules.payments.domain.errors')
PaymentRejectedError = _m.PaymentRejectedError
PaymentsDomainError = _m.PaymentsDomainError
