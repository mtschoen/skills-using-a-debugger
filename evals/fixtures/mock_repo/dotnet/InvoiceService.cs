using System.Collections.Generic;

namespace Billing;

public class InvoiceService
{
    private readonly Dictionary<string, Customer> _customers = new();

    // Throws NullReferenceException for some customer ids - origin unclear from the stack.
    public decimal TotalFor(string customerId)
    {
        Customer c = _customers.GetValueOrDefault(customerId);
        decimal total = 0;
        foreach (var line in c.Invoice.Lines)   // c or c.Invoice may be null
        {
            total += line.Amount;
        }
        return total;
    }
}

public class Customer
{
    public Invoice Invoice { get; set; }
}

public class Invoice
{
    public List<LineItem> Lines { get; set; } = new();
}

public class LineItem
{
    public decimal Amount { get; set; }
}
