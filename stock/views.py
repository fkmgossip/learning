from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from stock.models import Stock, AccountCurrency, AccountStock
from stock.forms import BuySellForm


def stock_list(request):
    stocks = Stock.objects.all()
    return render(request, 'stocks.html', {'stocks': stocks})


@login_required
def stock_detail(request, pk):
    stock = get_object_or_404(Stock, pk=pk)
    form = BuySellForm(initial={'price': stock.get_random_price()})
    return render(request, 'stock.html', {'stock': stock, 'form': form})


@login_required
def stock_buy(request, pk):
    if request.method != "POST":
        return redirect('stock:detail', pk=pk)
    
    stock = get_object_or_404(Stock, pk=pk)
    form = BuySellForm(request.POST)
    
    if form.is_valid():
        amount = form.cleaned_data['amount']
        price = form.cleaned_data['price']
        buy_cost = price * amount
        
        # Проверяем валютный счёт
        acc_currency, created = AccountCurrency.objects.get_or_create(
            account=request.user.account, currency=stock.currency,
            defaults={'amount': 0}
        )
        
        if acc_currency.amount < buy_cost:
            form.add_error(None, f'Недостаточно средств в валюте {stock.currency.sign}')
        else:
            # Обновляем акции
            acc_stock, created = AccountStock.objects.get_or_create(
                account=request.user.account, stock=stock,
                defaults={'average_buy_cost': 0, 'amount': 0}
            )
            current_cost = acc_stock.average_buy_cost * acc_stock.amount
            total_cost = current_cost + buy_cost
            total_amount = acc_stock.amount + amount
            
            acc_stock.amount = total_amount
            if total_amount > 0:
                acc_stock.average_buy_cost = total_cost / total_amount
            else:
                acc_stock.average_buy_cost = 0
            acc_stock.save()
            
            # Списываем средства
            acc_currency.amount = acc_currency.amount - buy_cost
            acc_currency.save()
            
            # Очищаем кэш
            cache.delete(f'currencies_{request.user.username}')
            cache.delete(f'stocks_{request.user.username}')
            
            return redirect('stock:list')
    
    return render(request, 'stock.html', {'stock': stock, 'form': form})


@login_required
def stock_sell(request, pk):
    if request.method != "POST":
        return redirect('stock:detail', pk=pk)
    
    stock = get_object_or_404(Stock, pk=pk)
    form = BuySellForm(request.POST)
    
    if form.is_valid():
        amount = form.cleaned_data['amount']
        price = form.cleaned_data['price']
        sell_value = price * amount
        
        try:
            acc_stock = AccountStock.objects.get(account=request.user.account, stock=stock)
        except AccountStock.DoesNotExist:
            form.add_error(None, f'У вас нет акций {stock.ticker}')
            return render(request, 'stock.html', {'stock': stock, 'form': form})
        
        if acc_stock.amount < amount:
            form.add_error(None, f'У вас только {acc_stock.amount} акций {stock.ticker}')
        else:
            acc_stock.amount = acc_stock.amount - amount
            
            if acc_stock.amount == 0:
                acc_stock.delete()
            else:
                acc_stock.save()
            
            acc_currency, created = AccountCurrency.objects.get_or_create(
                account=request.user.account, currency=stock.currency,
                defaults={'amount': 0}
            )
            acc_currency.amount = acc_currency.amount + sell_value
            acc_currency.save()
            
            cache.delete(f'currencies_{request.user.username}')
            cache.delete(f'stocks_{request.user.username}')
            
            return redirect('stock:list')
    
    return render(request, 'stock.html', {'stock': stock, 'form': form})


@login_required
def account(request):
    currencies = cache.get(f'currencies_{request.user.username}')
    stocks = cache.get(f'stocks_{request.user.username}')
    
    if currencies is None:
        currencies = [
            {'amount': acc_currency.amount, 'sign': acc_currency.currency.sign}
            for acc_currency in request.user.account.accountcurrency_set.select_related('currency')
        ]
        cache.set(f'currencies_{request.user.username}', currencies, 300)
    
    if stocks is None:
        stocks = [
            {'ticker': acc_stock.stock.ticker, 'amount': acc_stock.amount, 'avg': acc_stock.average_buy_cost}
            for acc_stock in request.user.account.accountstock_set.select_related('stock').all()
        ]
        cache.set(f'stocks_{request.user.username}', stocks, 300)
    
    return render(request, 'account.html', {'currencies': currencies, 'stocks': stocks})