class Debtor:
    def __init__(self, name, nickname, phone_number, debt_amount, transactions):
        self.name = name
        self.nickname = nickname
        self.phone_number = phone_number
        self.debt_amount = debt_amount
        self.transactions = transactions

    def to_dict(self):
        return {
            'name': self.name,
            'phone_number': self.phone_number,
            'debt_amount': self.debt_amount,
            'transactions': self.transactions
        }
