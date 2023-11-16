class Debtor:
    def __init__(self, name, nickname, phone_number, shop_id, debt_amount, transactions):
        self.name = name
        self.nickname = nickname
        self.phone_number = phone_number
        self.shop_id = shop_id
        self.debt_amount = debt_amount
        self.transactions = transactions

    def to_dict(self):
        return {
            'name': self.name,
            'nickname': self.nickname,
            'phone_number': self.phone_number,
            'shop_id': self.shop_id,
            'debt_amount': self.debt_amount,
            'transactions': self.transactions
        }

    def get_name(self):
        return self.name

    def get_nickname(self):
        return self.nickname

    def get_phone_number(self):
        return self.phone_number

    def get_shop_id(self):
        return self.shop_id

    def get_debt_amount(self):
        return self.debt_amount

    def get_transactions(self):
        return self.transactions
