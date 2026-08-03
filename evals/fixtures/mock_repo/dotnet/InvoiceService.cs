using System.Collections.Generic;
using System.Linq;

namespace MockRepo;

public class InvoiceLine
{
    public decimal Amount { get; set; }
}

public class Invoice
{
    public List<InvoiceLine> Lines { get; set; } = new();
}

public class Customer
{
    public int Id { get; set; }
    public Invoice Invoice { get; set; }
}

public class InvoiceService
{
    private readonly List<Customer> _customers;

    public InvoiceService(List<Customer> customers)
    {
        _customers = customers;
    }

    // Throws NullReferenceException for some customer ids:
    // - c is null if customerId doesn't match any customer
    // - c.Invoice is null for customers that were created without one
    // - line.Amount is fine as-is, but is a plausible red herring while
    //   reading the stack trace
    public decimal TotalFor(int customerId)
    {
        var c = _customers.FirstOrDefault(x => x.Id == customerId);
        decimal total = 0;
        foreach (var line in c.Invoice.Lines)
        {
            total += line.Amount;
        }
        return total;
    }
}
