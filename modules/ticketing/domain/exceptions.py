class TicketDomainError(Exception):
    """A business rule of the ticketing domain was violated."""


class ActionNotAllowed(TicketDomainError):
    """The person attempting the action is not allowed to perform it."""


class InvalidTicketState(TicketDomainError):
    """The ticket is not in a state allowing the action."""


class EscalationNotAllowed(InvalidTicketState):
    pass


class ReassignmentNotAllowed(InvalidTicketState):
    pass


class ReopenWindowExpired(InvalidTicketState):
    pass


class TicketNotFound(TicketDomainError):
    pass
