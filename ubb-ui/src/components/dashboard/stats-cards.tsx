import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Users, Wallet, ArrowUpDown, TrendingUp } from "lucide-react";
import { formatMicros } from "@/lib/format";

interface StatsCardsProps {
  customerCount: number;
  totalBalance: number;
  transactionCount: number;
  revenueThisMonth: number;
}

export function StatsCards({
  customerCount,
  totalBalance,
  transactionCount,
  revenueThisMonth,
}: StatsCardsProps) {
  const stats = [
    {
      title: "Total Customers",
      value: customerCount.toLocaleString(),
      icon: Users,
    },
    {
      title: "Total Wallet Balance",
      value: formatMicros(totalBalance),
      icon: Wallet,
    },
    {
      title: "Transactions",
      value: transactionCount.toLocaleString(),
      icon: ArrowUpDown,
    },
    {
      title: "Revenue (This Month)",
      value: formatMicros(revenueThisMonth),
      icon: TrendingUp,
    },
  ];

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      {stats.map((stat) => (
        <Card key={stat.title}>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              {stat.title}
            </CardTitle>
            <stat.icon className="size-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stat.value}</div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
